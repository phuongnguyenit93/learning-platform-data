# Lab: Managing Object Storage with CLI and Java SDK

## 1. Objectives and Lab Scenario

Within the **OCI Fundamentals Labs** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lab implements a file storage workflow for a Java application on Oracle Cloud Infrastructure. You will use the OCI CLI to prepare the bucket and data, then use the Java SDK to operate on those exact same resources.

Scenario: an application needs to store text files and CSV reports in a private bucket. The operations team uses the CLI to inspect; the application uses the SDK to upload, list, download, and delete. Both tools must share the same identity, region, namespace, and bucket so results can be cross-checked.

Upon completion, you will be able to:

- Distinguish between tenancy, compartment, Object Storage namespace, bucket, and object name.
- Set up API key authentication and explain the IAM permissions required for the lab.
- Create a private bucket; manipulate objects, metadata, and ETags using the CLI.
- Integrate the OCI Java SDK 3.x with Maven and an explicitly declared HTTP client.
- Paginate completely through listings, close streams properly, verify downloaded contents, and handle errors with request IDs.
- Clean up resources, explain cost-driving factors, and identify data-protection limitations of the lab setup.

Suggested duration: **90–120 minutes**, excluding tool installation and permission provisioning. This lab creates only one bucket with three small objects in a single region. VCN, Compute, and Oracle database services provide the deployment context of the module; you do not need to create those resources for this lab.

## 2. Resource Model and Values to Standardize

~~~mermaid
flowchart LR
    CLI["OCI CLI"] --> AUTH["API signing key and IAM"]
    JAVA["Java application"] --> AUTH
    AUTH --> OS["Object Storage in chosen region"]
    OS --> NS["Tenancy namespace"]
    NS --> B["Private bucket"]
    C["Lab compartment"] -. "contains bucket, defines IAM scope" .-> B
    B --> O1["Objects uploaded by CLI"]
    B --> O2["Object uploaded by Java"]
~~~

The namespace is not a child compartment. The diagram illustrates separate addressing and management relationships: a bucket belongs to a compartment while being accessed via the namespace and regional endpoint.

| Component | Role in this lab |
| --- | --- |
| Tenancy OCID | Identifies the tenancy in authentication config |
| User OCID, fingerprint, private key | Identity and signing material for API requests |
| Region | Selects the endpoint and where the bucket lives, e.g., `ap-singapore-1` |
| Compartment OCID | Where the bucket is created; IAM uses compartment scope to restrict permissions |
| Namespace | String assigned by OCI; do not derive it from tenancy name or tenancy OCID |
| Bucket name | Dedicated bucket name for this lab run |
| Object name | Full object key, e.g., `labs/run-01/cli/hello.txt` |
| ETag | Resource state identifier used for concurrency conditions |

Object Storage is a regional service. A tenancy's namespace name is identical across regions, yet looking up buckets still depends on the region being called. For the namespace-scoped buckets used in this lab, bucket names must be unique within the namespace in the corresponding region. Source: [Object Storage Overview](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm).

Forward slashes (`/`) in object names help organize by prefix; they do not create directory trees behaving like a POSIX filesystem. To fetch `labs/run-01/cli/hello.txt`, you must pass that exact full string, including casing and separators.

## 3. Environment and IAM Permissions Preparation

### 3.1. Tools and sample environment boundaries

The commands below use **Bash on Linux or WSL2**, along with `sha256sum` and `cmp`. On Windows, install the OCI CLI, JDK, and Maven inside the same WSL2 environment; the private key path in the config must also be valid inside WSL2. Do not paste raw Bash syntax into PowerShell.

Prepare:

- OCI CLI 3.x installed.
- JDK 17 and Maven 3.9.x.
- HTTPS connectivity to the Object Storage endpoint in the chosen region and to Maven repositories.
- A sandbox compartment, e.g., `OciObjectLab`.
- A user belonging to a lab-only group, e.g., `OciObjectLabUsers`.
- An API signing key with its public key registered to that user.

Verify tools:

~~~bash
oci --version
java -version
mvn -version
~~~

Check the `mvn -version` output to confirm Maven is actually using JDK 17. An API signing key for the OCI API is distinct from an SSH key for Compute login and distinct from a Customer Secret Key used for S3-compatible interfaces.

### 3.2. Policies for the lab

An administrator prepares the compartment, group, group membership, and policies before learners run commands. Example with the `Default` identity domain and a compartment directly under the tenancy:

~~~text
Allow group Default/OciObjectLabUsers to read objectstorage-namespaces in tenancy
Allow group Default/OciObjectLabUsers to manage buckets in compartment OciObjectLab
Allow group Default/OciObjectLabUsers to manage objects in compartment OciObjectLab
~~~

Substitute the actual identity domain, group, and compartment of your environment. If compartments are nested, identify the compartment appropriately for your tenancy's hierarchy. Attach the policy at the tenancy or an appropriate parent level for the granted scope; learners do not need permissions to edit IAM themselves.

The two `manage` statements allow creating, inspecting, and cleaning up resources in the sandbox compartment. This covers the full lab lifecycle and is broader than an application that only uploads or reads specific objects. Never grant `manage all-resources in tenancy` to resolve permission errors.

Bucket permissions and object permissions are separate layers. Being able to view or create a bucket does not mean you can read object contents. Creating new objects specifically requires `OBJECT_CREATE`; `use objects` alone is not enough for every `PutObject` call. Cross-check [Details for Object Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm) and [IAM Policies with Identity Domains](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm).

For production applications, separate bucket administration permissions from data-handling permissions. You can scope object policies to a single bucket using `target.bucket.name` conditions and select the exact permissions needed. A narrow policy only restricts access if the identity does not also receive broader permissions from another group or policy.

### 3.3. Shared API key configuration for CLI and SDK

Create or append the `LAB` profile in `~/.oci/config`. The values below are placeholders and must be replaced with your environment's real details:

~~~ini
[LAB]
user=ocid1.user.oc1..REPLACE_WITH_USER_OCID
fingerprint=REPLACE_WITH_REGISTERED_PUBLIC_KEY_FINGERPRINT
tenancy=ocid1.tenancy.oc1..REPLACE_WITH_TENANCY_OCID
region=ap-singapore-1
key_file=/home/your-user/.oci/oci_api_key.pem
~~~

The private key must match the public key registered for that exact user. If the key is encrypted, configure an appropriate runtime passphrase mechanism for both CLI and Java; the sample code below has no interactive passphrase prompt. Never copy private keys, passphrases, or config contents into source code, objects, or lab reports. See [SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm).

On Linux/WSL2, restrict file permissions to your current user:

~~~bash
chmod 700 "$HOME/.oci"
chmod 600 "$HOME/.oci/config"
chmod 600 "$HOME/.oci/oci_api_key.pem"
~~~

If the key resides at another path, adjust the path in the final command. On WSL2, store keys inside the WSL Linux filesystem for consistent file permission handling.

## 4. Initialize Session and Verify Connectivity

Keep the same Bash session for the entire lab. Update region and compartment OCID before running:

~~~bash
set -euo pipefail

export OCI_LAB_CONFIG_FILE="$HOME/.oci/config"
export OCI_LAB_PROFILE="LAB"
export OCI_LAB_REGION="ap-singapore-1"
export OCI_LAB_COMPARTMENT_OCID="ocid1.compartment.oc1..REPLACE_ME"

export OCI_LAB_RUN_ID="$(date -u +%Y%m%d%H%M%S)-$RANDOM"
export OCI_LAB_BUCKET="oci-os-lab-$OCI_LAB_RUN_ID"
export OCI_LAB_PREFIX="labs/$OCI_LAB_RUN_ID/"
export OCI_LAB_CLI_TEXT_KEY="${OCI_LAB_PREFIX}cli/hello.txt"
export OCI_LAB_CLI_CSV_KEY="${OCI_LAB_PREFIX}cli/metrics.csv"
export OCI_LAB_JAVA_KEY="${OCI_LAB_PREFIX}java/hello.txt"

oci_lab() {
  oci --config-file "$OCI_LAB_CONFIG_FILE" \
      --profile "$OCI_LAB_PROFILE" \
      --auth api_key \
      --region "$OCI_LAB_REGION" "$@"
}

export OCI_LAB_NAMESPACE="$(
  oci_lab os ns get --query data --raw-output
)"

test -n "$OCI_LAB_NAMESPACE"
printf 'region=%s\nnamespace=%s\nbucket=%s\n' \
  "$OCI_LAB_REGION" "$OCI_LAB_NAMESPACE" "$OCI_LAB_BUCKET"

mkdir -p "$HOME/oci-object-lab/$OCI_LAB_RUN_ID"
cd "$HOME/oci-object-lab/$OCI_LAB_RUN_ID"
mkdir -p data downloads src/main/java/lab
~~~

The `oci_lab` helper pins the config, profile, auth type, and region for each command. Java will read the corresponding `OCI_LAB_*` variables; this is a convention of our lab program, not a set of environment variables automatically recognized by the SDK.

`os ns get` succeeding proves the namespace lookup request was authenticated and processed. It does not yet prove you have permissions to create buckets, upload, or delete objects. If this step fails, resolve authentication and connectivity before continuing. CLI usage and auth options are described in [Using the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliusing.htm).

## 5. Part A — Manage Bucket and Objects with OCI CLI

### 5.1. Create and verify a private bucket

~~~bash
oci_lab os bucket create \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --compartment-id "$OCI_LAB_COMPARTMENT_OCID" \
  --name "$OCI_LAB_BUCKET" \
  --public-access-type NoPublicAccess \
  --storage-tier Standard \
  --versioning Disabled

oci_lab os bucket get \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --name "$OCI_LAB_BUCKET"
~~~

Confirm the result:

| Property | Expected value |
| --- | --- |
| `name` | Equals `OCI_LAB_BUCKET` |
| `compartment-id` | Equals the chosen compartment OCID |
| `public-access-type` | `NoPublicAccess` |
| `storage-tier` | `Standard` |
| `versioning` | `Disabled` |

The lab chooses Standard for immediate reads during practice and disables versioning so cleanup only needs to handle current objects. Parameters and valid values are listed in [CLI bucket create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/create.html).

A private bucket is still accessed through a publicly routable service endpoint; `NoPublicAccess` blocks anonymous access and does not by itself create a private network path. In a Compute-in-private-subnet architecture, traffic to Object Storage can be routed through a service gateway; both network connectivity and IAM permissions must still be valid.

### 5.2. Create sample data and upload two objects

~~~bash
cat > data/hello.txt <<'EOF'
Hello OCI Object Storage.
This file is used to cross-check data between the CLI and Java SDK.
EOF

cat > data/metrics.csv <<'EOF'
service,requests
catalog,12
checkout,7
EOF

sha256sum data/hello.txt data/metrics.csv

oci_lab os object put \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_CLI_TEXT_KEY" \
  --file data/hello.txt \
  --content-type 'text/plain; charset=utf-8' \
  --metadata '{"lab":"oci-fundamentals","writer":"cli"}' \
  --no-multipart \
  --no-overwrite

oci_lab os object put \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_CLI_CSV_KEY" \
  --file data/metrics.csv \
  --content-type 'text/csv; charset=utf-8' \
  --metadata '{"lab":"oci-fundamentals","writer":"cli"}' \
  --no-multipart \
  --no-overwrite
~~~

`--name` sets the full object name, independent of the local file path. `--no-overwrite` prevents accidental overwrites when re-running commands; inspect the output because skipping an existing object is not a fresh upload. `--no-multipart` keeps the upload path simple for payloads of a few KB. Metadata describes the object and does not replace file contents or access control. Source: [CLI object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

### 5.3. List by exact prefix and read metadata

~~~bash
oci_lab os object list \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --prefix "$OCI_LAB_PREFIX" \
  --fields name,size,timeCreated \
  --all

oci_lab os object head \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_CLI_TEXT_KEY"

CLI_TEXT_ETAG="$(
  oci_lab os object head \
    --namespace-name "$OCI_LAB_NAMESPACE" \
    --bucket-name "$OCI_LAB_BUCKET" \
    --name "$OCI_LAB_CLI_TEXT_KEY" \
    --query etag --raw-output
)"
test -n "$CLI_TEXT_ETAG"
printf 'CLI text ETag=%s\n' "$CLI_TEXT_ETAG"
~~~

At this point there must be **two objects** under the run's prefix. `--all` instructs the CLI to fetch all result pages; do not combine it with `--limit`. `head` retrieves object metadata without downloading the body. See [CLI object list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/list.html) and [CLI object head](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/head.html).

Preserve the exact ETag returned by the service when using `If-Match` conditions. Do not strip characters, recompute an ETag from file content, or assume the ETag is a SHA-256 hash.

### 5.4. Download and verify contents

~~~bash
oci_lab os object get \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_CLI_TEXT_KEY" \
  --file downloads/hello-cli.txt

cmp data/hello.txt downloads/hello-cli.txt
sha256sum data/hello.txt downloads/hello-cli.txt
~~~

`cmp` returning `0` and identical SHA-256 digests prove the downloaded data matches the original data. Command success or matching byte sizes alone is not enough proof. `--file` specifies the destination file on the machine running the CLI, while `--name` is the object name in OCI. See [CLI object get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/get.html).

## 6. Part B — Build the Java SDK Program

### 6.1. Maven project structure and dependencies

Inside the working directory created earlier, save these two files:

~~~text
oci-object-lab/<run-id>/
├── pom.xml
├── src/main/java/lab/ObjectStorageLab.java
├── data/
└── downloads/
~~~

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>vn.learning</groupId>
  <artifactId>oci-object-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <oci.sdk.version>3.102.0</oci.sdk.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.oracle.oci.sdk</groupId>
        <artifactId>oci-java-sdk-bom</artifactId>
        <version>${oci.sdk.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>com.oracle.oci.sdk</groupId>
      <artifactId>oci-java-sdk-objectstorage</artifactId>
    </dependency>
    <dependency>
      <groupId>com.oracle.oci.sdk</groupId>
      <artifactId>oci-java-sdk-common-httpclient-jersey3</artifactId>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>lab.ObjectStorageLab</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

SDK version `3.102.0` is pinned for this sample and has an [official Oracle release](https://github.com/oracle/oci-java-sdk/releases/tag/v3.102.0). When upgrading versions, upgrade consistently via the BOM and re-verify compatibility.

SDK 3.x requires applications to explicitly select an HTTP client. This sample picks Jersey 3; omitting this dependency can prevent the program from initializing an HTTP provider. See [Java SDK Getting Started](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm) and [Oracle SDK 3.x Notes](https://github.com/oracle/oci-java-sdk/blob/v3.102.0/README.md).

### 6.2. Source code implementing four operations

Save the following to `src/main/java/lab/ObjectStorageLab.java`:

~~~java
package lab;

import com.oracle.bmc.ClientConfiguration;
import com.oracle.bmc.ConfigFileReader;
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.model.BmcException;
import com.oracle.bmc.objectstorage.ObjectStorageClient;
import com.oracle.bmc.objectstorage.requests.DeleteObjectRequest;
import com.oracle.bmc.objectstorage.requests.GetObjectRequest;
import com.oracle.bmc.objectstorage.requests.ListObjectsRequest;
import com.oracle.bmc.objectstorage.requests.PutObjectRequest;
import com.oracle.bmc.retrier.RetryConfiguration;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public final class ObjectStorageLab {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }

    private static void upload(
            ObjectStorageClient client, String namespace, String bucket,
            String key, Path source) throws Exception {
        if (!Files.isRegularFile(source)) {
            throw new IllegalArgumentException("Not a regular file: " + source);
        }
        long length = Files.size(source);
        if (length > 16L * 1024 * 1024) {
            throw new IllegalArgumentException("Lab upload is limited to 16 MiB");
        }

        try (InputStream input = Files.newInputStream(source)) {
            var response = client.putObject(PutObjectRequest.builder()
                    .namespaceName(namespace)
                    .bucketName(bucket)
                    .objectName(key)
                    .contentLength(length)
                    .contentType("text/plain; charset=utf-8")
                    .opcMeta(Map.of("lab", "oci-fundamentals", "writer", "java-sdk"))
                    .ifNoneMatch("*")
                    .retryConfiguration(RetryConfiguration.NO_RETRY_CONFIGURATION)
                    .putObjectBody(input)
                    .build());
            System.out.printf("PUT key=%s etag=%s requestId=%s%n",
                    key, response.getETag(), response.getOpcRequestId());
        }
    }

    private static void list(
            ObjectStorageClient client, String namespace, String bucket,
            String prefix) {
        String nextStart = null;
        int pageNumber = 0;
        do {
            var response = client.listObjects(ListObjectsRequest.builder()
                    .namespaceName(namespace)
                    .bucketName(bucket)
                    .prefix(prefix)
                    .fields("name,size,timeCreated")
                    .limit(2)
                    .start(nextStart)
                    .build());

            var body = response.getListObjects();
            pageNumber++;
            System.out.printf("LIST page=%d requestId=%s%n",
                    pageNumber, response.getOpcRequestId());
            for (var object : body.getObjects()) {
                System.out.printf("  name=%s size=%s%n",
                        object.getName(), object.getSize());
            }
            nextStart = body.getNextStartWith();
        } while (nextStart != null && !nextStart.isEmpty());
    }

    private static void download(
            ObjectStorageClient client, String namespace, String bucket,
            String key, Path destination) throws Exception {
        if (Files.exists(destination)) {
            throw new IllegalArgumentException(
                    "Destination already exists: " + destination);
        }

        var response = client.getObject(GetObjectRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucket)
                .objectName(key)
                .build());
        try (InputStream input = response.getInputStream()) {
            long copied = Files.copy(input, destination);
            System.out.printf("GET key=%s bytes=%d etag=%s requestId=%s%n",
                    key, copied, response.getETag(), response.getOpcRequestId());
        }
    }

    private static void delete(
            ObjectStorageClient client, String namespace, String bucket,
            String key, String expectedEtag) {
        var response = client.deleteObject(DeleteObjectRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucket)
                .objectName(key)
                .ifMatch(expectedEtag)
                .build());
        System.out.printf("DELETE key=%s requestId=%s%n",
                key, response.getOpcRequestId());
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "Usage: put <key> <file> | list <prefix> | "
                    + "get <key> <file> | delete <key> <etag>");
        }

        int expectedArguments = switch (args[0]) {
            case "list" -> 2;
            case "put", "get", "delete" -> 3;
            default -> throw new IllegalArgumentException(
                    "Unknown operation: " + args[0]);
        };
        if (args.length != expectedArguments) {
            throw new IllegalArgumentException("Wrong number of arguments");
        }

        String namespace = requiredEnv("OCI_LAB_NAMESPACE");
        String bucket = requiredEnv("OCI_LAB_BUCKET");
        var config = ConfigFileReader.parse(
                requiredEnv("OCI_LAB_CONFIG_FILE"),
                requiredEnv("OCI_LAB_PROFILE"));
        var provider = new ConfigFileAuthenticationDetailsProvider(config);

        try (var client = ObjectStorageClient.builder()
                .region(Region.fromRegionId(requiredEnv("OCI_LAB_REGION")))
                .configuration(ClientConfiguration.builder()
                        .connectionTimeoutMillis(10_000)
                        .readTimeoutMillis(60_000)
                        .build())
                .build(provider)) {
            switch (args[0]) {
                case "put" ->
                        upload(client, namespace, bucket, args[1], Path.of(args[2]));
                case "list" ->
                        list(client, namespace, bucket, args[1]);
                case "get" ->
                        download(client, namespace, bucket, args[1], Path.of(args[2]));
                case "delete" ->
                        delete(client, namespace, bucket, args[1], args[2]);
                default -> throw new IllegalStateException("Unexpected operation");
            }
        } catch (BmcException error) {
            System.err.printf("OCI_ERROR status=%d code=%s requestId=%s%n",
                    error.getStatusCode(),
                    error.getServiceCode(),
                    error.getOpcRequestId());
            throw error;
        }
    }
}
~~~

Design choices to understand in the code:

- `put` uses `ifNoneMatch("*")` to require creating the object only when the name does not yet exist. This is a service-side condition, unlike checking existence first and then uploading on the client side.
- Upload size is intentionally capped at 16 MiB in this sample. For large files, use multipart uploads or `UploadManager` after designing retry handling and incomplete-upload cleanup.
- Uploads disable automatic retries because the input stream in this sample is not designed to be arbitrarily replayed. If a timeout occurs after sending data, inspect the object before deciding to retry.
- `list` requests `size` in `fields` and uses a page size of two to observe pagination.
- `get` reads via a stream, closes the stream with `try-with-resources`, and refuses to overwrite an existing destination file. Ensure the parent directory exists beforehand.
- `delete` accepts an expected ETag to avoid deleting an object updated by another actor.
- `BmcException` logs the status code, service code, and request ID before rethrowing; failed calls are never reported as successes.

Upload parameters and ETag conditions are documented at [PutObjectRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/PutObjectRequest.Builder.html); delete conditions at [DeleteObjectRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/DeleteObjectRequest.Builder.html). Disabling retries uses [RetryConfiguration](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/retrier/RetryConfiguration.html).

Specifically, `ListObjects` returns the next-page token in the **body** via `getNextStartWith()`; pass it back via `start(...)`. Do not assume every OCI listing API uses the same pagination header. See [ListObjects](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/model/ListObjects.html) and [ListObjectsRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/ListObjectsRequest.Builder.html).

## 7. Run Java and Test Two-Way Interoperability with CLI

### 7.1. Compile and upload the third object

~~~bash
mvn -q -DskipTests compile

mvn -q exec:java \
  "-Dexec.args=put $OCI_LAB_JAVA_KEY data/hello.txt"

oci_lab os object head \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_JAVA_KEY"
~~~

Java outputs a `PUT` line with an ETag and request ID. The CLI must be able to read the newly created object, with metadata showing `writer=java-sdk`. Request IDs from different commands are not expected to match.

### 7.2. Java lists all data created by both tools

~~~bash
mvn -q exec:java \
  "-Dexec.args=list $OCI_LAB_PREFIX"
~~~

There are three objects under the run's prefix: two created by the CLI and one created by the SDK. With `limit(2)`, observe the program stepping through pages until `nextStartWith` is exhausted rather than stopping after the first page.

Example output shape, where values in `<...>` vary by environment:

~~~text
LIST page=1 requestId=<request-id-1>
  name=labs/<run-id>/cli/hello.txt size=<bytes>
  name=labs/<run-id>/cli/metrics.csv size=<bytes>
LIST page=2 requestId=<request-id-2>
  name=labs/<run-id>/java/hello.txt size=<bytes>
~~~

This is an illustrative output for reference, not a log from a live pre-run deployment.

### 7.3. Java reads CLI object; CLI reads Java object

~~~bash
mvn -q exec:java \
  "-Dexec.args=get $OCI_LAB_CLI_TEXT_KEY downloads/hello-sdk.txt"

oci_lab os object get \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_JAVA_KEY" \
  --file downloads/java-via-cli.txt

cmp data/hello.txt downloads/hello-sdk.txt
cmp data/hello.txt downloads/java-via-cli.txt

sha256sum \
  data/hello.txt \
  downloads/hello-cli.txt \
  downloads/hello-sdk.txt \
  downloads/java-via-cli.txt
~~~

All four SHA-256 digests must match. This confirms both tools access the same underlying data while exercising read paths through both CLI and Java.

If the network drops while `Files.copy` is reading the stream, a partial downloaded file may remain on disk. Never treat that partial file as valid; inspect contents, handle the incomplete file separately, and download again to a fresh path. Production applications should download to a temporary file and rename it after verification succeeds.

## 8. Test a Controlled Failure and Understand Concurrency Conditions

Re-run the Java `put` operation with the same existing object name. Wrap it in `if` so the expected error does not make `set -e` abort the entire session:

~~~bash
if mvn -q exec:java \
  "-Dexec.args=put $OCI_LAB_JAVA_KEY data/hello.txt"; then
  printf 'FAIL: duplicate creation succeeded unexpectedly.\n'
else
  printf 'Check the OCI_ERROR line; pass only if status=412 due to duplicate-creation condition.\n'
fi
~~~

Because the sample sets `ifNoneMatch("*")`, the duplicate creation must be rejected with HTTP `412` while the object still exists. A Maven, network, or authentication error also produces a non-zero exit code, but does not prove the duplicate-creation condition worked. You must inspect `OCI_ERROR` and verify the exact cause.

To understand update operations without turning this lab into another application:

| Intent | Appropriate condition | When condition no longer holds |
| --- | --- | --- |
| Create new object only | `If-None-Match: *` | Does not overwrite an existing object |
| Overwrite only the read state | `If-Match: <read ETag>` | Returns precondition error instead of overwriting newer state |
| Delete only the verified state | `If-Match: <read ETag>` | Does not delete an object just updated elsewhere |

In the CLI, `object put --if-match` supports conditional updates. `--force` only skips the tool's interactive overwrite prompt; it does not bypass service-side ETag checking.

If an application hits a precondition failure, re-read the state and decide according to business logic. Never blindly strip `If-Match` or `If-None-Match` to force an operation through.

## 9. Layer-by-Layer Error Diagnostics

| Symptom | What to check first | Resolution |
| --- | --- | --- |
| `401` or signature error | Profile, user OCID, key, fingerprint, system clock | Check the public key of the right user and clock sync; do not change IAM randomly |
| `403`, or `404 NotAuthorizedOrNotFound` | IAM permissions and full resource addressing | Check both permissions and region, namespace, bucket, object name; 404 does not always mean nonexistent |
| Can fetch namespace but upload fails | Policy for `objects` | Check object-creation permissions and the bucket's compartment scope |
| Java and CLI see different data | All four values: region, namespace, bucket, prefix | Print non-sensitive values from the lab session to cross-check |
| Only two objects visible in Java | `nextStartWith` token | Ensure the loop passes `start` back and runs to completion |
| HTTP provider fails to initialize | HTTP client dependency and SDK version | Verify Jersey 3 is present and all modules share the same BOM |
| `412` | Creation condition or ETag | Determine whether the object already exists or state changed; handle per business intent |
| `429` or `5xx` | Request ID, call rate, and connectivity | Cap retries, use jittered backoff, and ensure requests are replayable |
| Downloaded file missing or wrong hash | Stream, path, partial download | Discard the bad file; re-download after identifying the root cause |
| Bucket deletion reports remaining data | Other objects, versions, or incomplete multipart uploads | Inventory resources first; do not immediately switch to bulk force deletion |

You can inspect resolved dependencies with:

~~~bash
mvn dependency:tree -Dincludes=com.oracle.oci.sdk
~~~

For errors requiring investigation, record the UTC timestamp, operation, region, bucket, object name, error code, and request ID. Restrict sharing of OCIDs and internal paths per team rules. Never include private keys or unreviewed full debug logs in reports.

## 10. Cost, Observability, and Deployment Choices

### 10.1. Keep costs small

This sample uses only three tiny objects and the Standard tier. In real operations, monitor storage capacity, request counts, outbound data transfer, and any enabled add-on features. Never assume a lab is always free based on account tier names.

Using a dedicated bucket per run keeps inventory and cleanup clear. You can apply tags per organizational policy and set budgets for alerting; budget alerts are not an automatic kill switch for spending.

Do not enable Archive, lifecycle tier transitions, replication, or retention rules just to complete this lab. Those features require planning for retrieval times, service permissions, data retention periods, and associated costs.

### 10.2. Observability and availability

Logging in the Java code ties an application operation to a service request. In the OCI Console, open the right bucket and inspect Monitoring to observe relevant metrics; wait for monitoring data to populate before concluding there was no activity.

Object Storage provides regional storage independent of any single Compute instance lifecycle. That does not automatically protect data against valid delete operations or region-wide outages. For production systems, define RPO/RTO first, then select appropriate versioning, retention, copies, and replication; testing data recovery is a separate step.

This lab disables versioning to simplify cleanup. Therefore, do not use this configuration as a template for protecting critical data. The sample code also does not implement multipart uploads, atomic downloads, replayable upload retries, or post-failure recovery.

When an application runs on OCI Compute, you can replace on-disk API keys with instance principals plus dynamic groups and corresponding policies. You cannot simply remove the config file while keeping the current auth provider; both CLI and Java must switch to the appropriate principal provider. Never grant extra permissions or make a bucket public instead of configuring authentication properly.

## 11. Delete Objects with SDK and CLI, Then Delete the Bucket

Only clean up the newly created bucket after saving required evidence. The commands below assume versioning remains `Disabled` and no other actor added data to the bucket.

### 11.1. Java deletes the object it created

Fetch the latest ETag from the service and pass the exact value to Java. Quoting inside `exec.args` preserves the ETag as a single argument:

~~~bash
JAVA_ETAG="$(
  oci_lab os object head \
    --namespace-name "$OCI_LAB_NAMESPACE" \
    --bucket-name "$OCI_LAB_BUCKET" \
    --name "$OCI_LAB_JAVA_KEY" \
    --query etag --raw-output
)"
test -n "$JAVA_ETAG"

mvn -q exec:java \
  "-Dexec.args=delete $OCI_LAB_JAVA_KEY '$JAVA_ETAG'"
~~~

If the ETag changed between `head` and `delete`, the conditional delete must fail. Investigate the change before fetching a new ETag and deciding again. Do not drop the condition just to force deletion through.

### 11.2. CLI deletes the remaining two objects

~~~bash
oci_lab os object delete \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_CLI_TEXT_KEY" \
  --if-match "$CLI_TEXT_ETAG" \
  --force

oci_lab os object delete \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_CLI_CSV_KEY" \
  --force

oci_lab os object list \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --all \
  --query 'length(data)'
~~~

The count result must be `0`. At this step, check the entire bucket, not just the session prefix. `--force` skips the interactive delete prompt, while `--if-match` keeps the state precondition on the text object. See [CLI object delete](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/delete.html).

### 11.3. Delete the empty bucket and verify

~~~bash
printf 'About to delete lab bucket: %s\n' "$OCI_LAB_BUCKET"

oci_lab os bucket delete \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --name "$OCI_LAB_BUCKET" \
  --force
~~~

Standard bucket deletion requires the bucket to be empty. Do not use `--empty` in this workflow because each remaining resource should be inspected before deletion. See [CLI bucket delete](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/delete.html).

After the command succeeds, verify the bucket no longer appears in the bucket list for the right compartment and region:

~~~bash
oci_lab os bucket list \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --compartment-id "$OCI_LAB_COMPARTMENT_OCID" \
  --all \
  --query 'data[].name'
~~~

If the bucket cannot be deleted even though the current object list is empty, check versioning, previous object versions, incomplete multipart uploads, retention rules, and related settings. Do not apply this three-object workflow verbatim to a shared bucket.

Only revoke API keys or policies if they were created specifically for this lab session and are no longer needed. Never delete keys, groups, or policies shared by other labs or applications.

## 12. Lab Completion Evidence

| Verification item | Required evidence |
| --- | --- |
| Correct resource scope | Region, namespace, bucket, and compartment used |
| Private bucket | `bucket get` output showing `NoPublicAccess` |
| CLI data operations | Both objects present, metadata readable, downloaded content matches |
| Java object creation | `PUT` output line and CLI read-back of that object |
| Java full pagination | All three objects read across result pages |
| CLI and Java cross-reads | Passing `cmp` checks and matching SHA-256 digests |
| Duplicate-prevention condition | `412` error in the right context, original data still readable |
| Error handling and tracing | Error code and request ID captured when the service rejects a call |
| Object and bucket cleanup | Whole bucket at `0` objects, bucket deleted, and bucket list rechecked |

Reports must contain only sanitized output with sensitive data removed. If a step was not executed, state clearly that it was not run rather than substituting the illustrative logs from this guide. The expected outcome is a repeatable private storage workflow with verified data integrity and lab resources cleaned up at the end.
