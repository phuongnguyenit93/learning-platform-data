# OKE Workload Identity and Accessing OCI Services

In the **Kubernetes with OKE** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson connects Kubernetes with Oracle Cloud Infrastructure's (OCI) authorization model: an application running inside a Pod needs to read data from Object Storage, fetch secret configuration, or call an OCI service without carrying a user's API signing key.

The goal is to implement application-bound access permissions, understand the relationship between tenancy, compartment, Kubernetes ServiceAccount, and IAM, and operate the network path, logging, and permission lifecycle. The lab uses a Java program reading an existing object in a private bucket; negative tests help confirm permission boundaries.

## 1. Where Does a Workload's Identity Live?

Suppose a reporting application has three replicas spread across two worker nodes. All three Pods need to read the same bucket, while a billing application running on the same nodes must not read that bucket. Granting permissions per node makes separating the two applications hard to manage. Copying OCI keys into each Pod forces the system to protect and rotate additional credential copies.

OKE workload identity uses the tuple:

~~~text
(cluster OCID, Kubernetes namespace, Kubernetes ServiceAccount)
~~~

Pods using the same tuple share a workload identity from IAM's perspective. Scaling replicas or replacing Pods does not create a separate IAM identity for each replica. Workload identity requires an **enhanced cluster** and does not use dynamic groups to aggregate workloads. [Oracle: Granting Workloads Access to OCI Resources](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

Running example throughout this lesson:

| Component | Illustrative Value | Role |
| --- | --- | --- |
| Cluster | `<CLUSTER_OCID>` | Distinguishes the production cluster from other clusters |
| Kubernetes namespace | `reporting` | Application organization boundary inside the cluster |
| ServiceAccount | `report-reader` | Identity assigned to Pods |
| OCI Compartment | `<LAB_COMPARTMENT_OCID>` | Holds the lab cluster and bucket |
| Private bucket | `oke-report-input` | Resource granted read access |
| Existing object | `samples/orders.csv` | Non-sensitive test data |

**Kubernetes namespace** and **Object Storage namespace** are two distinct concepts. Namespace `reporting` only has meaning inside Kubernetes; the Object Storage namespace is the tenancy's storage namespace name used in Object Storage APIs. Do not pass the Kubernetes namespace name into the OCI SDK's `namespaceName` parameter.

One design implication: two components with different permissions need different ServiceAccounts, even if they belong to the same business application. Do not share `report-reader` across every Deployment in a namespace and expect IAM to differentiate based on Deployment name or Pod labels.

## 2. Three Layers That Decide Whether a Request Succeeds

A successful object read requires all three simultaneously:

1. **Valid identity:** the program uses the right provider, has a ServiceAccount token, and runs in a supported OKE environment.
2. **Valid permissions:** IAM permits the exact principal to perform the action on the target resource.
3. **Valid connectivity:** the Pod can reach the authentication flow and service endpoint, with proper DNS, TLS, and routes.

Kubernetes RBAC governs permissions against the Kubernetes API, such as reading ConfigMaps or creating Jobs. OCI IAM governs permissions against OCI services. Granting a `ClusterRoleBinding` does not replace an object-read policy; conversely, an Object Storage policy does not grant permission to read Kubernetes Secrets. [Kubernetes: Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

| Authentication Method | Represented Identity | Considerations for In-Pod Applications |
| --- | --- | --- |
| User API signing key | IAM user owning the key | Must store, rotate, and revoke key copies |
| Instance principal | Compute instance | Permissions tied to node; does not create per-application boundaries |
| OKE workload identity | Tuple of cluster, namespace, ServiceAccount | Suitable when granting permissions per workload |
| Kubernetes ServiceAccount token used with Kubernetes API | ServiceAccount in cluster | This token does not become OCI permission just by being mounted in a Pod |

The table above helps choose permission boundaries. Workload identity reduces the need to distribute user keys, yet the token remains a credential that must be protected.

## 3. Authentication Flow via the OCI SDK

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant P as Pod reporting/report-reader
    participant S as OCI SDK in application
    participant I as OKE/OCI authentication infrastructure
    participant O as Object Storage + IAM
    K->>P: Mount ServiceAccount token into Pod
    P->>S: Call GetObject
    S->>I: Use OKE workload identity provider
    I-->>S: Session credentials
    S->>O: Signed request to target object
    O->>O: Evaluate IAM policy
    O-->>S: Data or denial error
~~~

This is a conceptual diagram for locating where failures occur; the application lets the SDK handle the authentication protocol and request signing. Do not manually send the Kubernetes token as a bearer token to Object Storage.

In modern Kubernetes configurations, ServiceAccount tokens are mounted via projected volumes, are time-bound, and are rotated by kubelet. The lab retains standard mounting so the provider can read the token; do not manually create long-lived token Secrets. [Kubernetes: Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/)

Create one `OkeWorkloadIdentityAuthenticationDetailsProvider` reused per process rather than creating a new provider for every HTTP request. For long-running Java services, manage the provider and OCI clients as singletons with clear lifecycles. The SDK caches credentials; repeated instantiation increases token fetches. [Oracle: provider usage guide](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

Applications still call service APIs via the SDK; workload identity is not a way to log into the OCI Console. In this lesson, the OCI CLI on the admin host prepares resources, while in-Pod requests are signed by the Java provider.

## 4. Writing IAM Policies by Resource and Required Actions

### 4.1. Policy to Read Objects Only in One Bucket

An IAM administrator creates a policy at a scope covering the bucket's compartment. Replace both OCID placeholders with real values:

~~~text
Allow any-user to read objects in compartment id <LAB_COMPARTMENT_OCID> where all {
  request.principal.type = 'workload',
  request.principal.cluster_id = '<CLUSTER_OCID>',
  request.principal.namespace = 'reporting',
  request.principal.service_account = 'report-reader',
  target.bucket.name = 'oke-report-input'
}
~~~

Each condition serves a specific role:

| Condition | Constraint Enforced |
| --- | --- |
| `request.principal.type` | Request is authenticated with a workload identity |
| `request.principal.cluster_id` | Matches the approved cluster |
| `request.principal.namespace` | Matches the application's namespace |
| `request.principal.service_account` | Matches the data-reading component's ServiceAccount |
| `target.bucket.name` | Matches the input bucket |

`any-user` is the subject in conditional policy syntax. Permissions still depend on the entire `where all` expression; the bucket does not become public because of it. When reviewing, check the `Allow` clause, compartment scope, and every condition, rather than looking at `any-user` in isolation.

For Object Storage, `read objects` includes reading content and object inspection permissions, so it does not allow solely `GetObject`. It does not grant bucket creation or object write/delete permissions. Bucket name conditions are compared case-insensitively by IAM; avoid designing two buckets whose permission boundary differs only by letter case. [Oracle: Object Storage policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm)

The lab pre-supplies the Object Storage namespace, bucket, and object. The program does not list all buckets to discover resources. This keeps the API scope in the example aligned with input-reading needs.

### 4.2. Permissions Can Come from Multiple Policies

If another policy already grants broader access to the same principal, the narrow policy above does not revoke that broader access. When a write test unexpectedly succeeds, inspect policies applied at the tenancy and related compartments rather than looking only at the newly created policy.

Omitting a condition such as cluster OCID also changes the trust model. A test cluster might use the same namespace and ServiceAccount names as production; keeping the cluster OCID separates the two environments in this policy.

## 5. Hands-On: Java Job Reading Object Storage

### 5.1. Preparation and Conventions

Use a lab environment with these prerequisites:

- An active OKE enhanced cluster; deployer has their own kubeconfig and permission to create Namespaces, ServiceAccounts, and Jobs within the lab scope.
- Cluster and bucket reside in **the same OCI compartment** for the main exercise. Section 7 covers the cross-compartment case.
- An administrator has created private bucket `oke-report-input` and pre-uploaded a small object `samples/orders.csv`. Do not use a bucket holding real data for permission tests.
- Build host has Docker; shell commands below use Bash syntax. Manifest-transforming tests additionally require `jq`.
- A container registry and image pull path are ready. If the repository is private, configure image pulls per your registry mechanism before running the Job.
- The policy from section 4 is applied, and network paths from workloads to the service are ready.

Record configuration values:

| Variable in Example | Source |
| --- | --- |
| `<CLUSTER_OCID>` | OKE cluster details |
| `<LAB_COMPARTMENT_OCID>` | Compartment containing the lab cluster and bucket |
| `<OCI_REGION>` | Region containing the bucket, e.g., `ap-singapore-1` |
| `<OBJECT_STORAGE_NAMESPACE>` | Tenancy's Object Storage namespace |
| `<REGISTRY>/<REPOSITORY>:<TAG>` | Image to build and push to registry |

No private key, fingerprint, or `~/.oci/config` profile needs to be supplied to the container. Region and resource names are routing/target configuration, not substitutes for IAM permissions.

### 5.2. Creating Namespace and ServiceAccounts

Contents of `identity.yaml` in the learner's lab directory:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: reporting
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: report-reader
  namespace: reporting
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: report-untrusted
  namespace: reporting
~~~

Apply:

~~~bash
kubectl apply -f identity.yaml
kubectl get serviceaccount -n reporting
~~~

`report-untrusted` is for the negative test and must not be included in the bucket-read policy. The example creates no RoleBinding for the application because the application has no business need to call the Kubernetes API.

### 5.3. Declaring the OCI SDK for Java

Create a Maven project with class `src/main/java/vn/example/oke/ObjectAccessProbe.java`. Use the following `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>oke-object-access-probe</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <oci.sdk.version>3.88.0</oci.sdk.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.oracle.oci.sdk</groupId>
            <artifactId>oci-java-sdk-addons-oke-workload-identity</artifactId>
            <version>${oci.sdk.version}</version>
        </dependency>
        <dependency>
            <groupId>com.oracle.oci.sdk</groupId>
            <artifactId>oci-java-sdk-objectstorage</artifactId>
            <version>${oci.sdk.version}</version>
        </dependency>
        <dependency>
            <groupId>com.oracle.oci.sdk</groupId>
            <artifactId>oci-java-sdk-common-httpclient-jersey3</artifactId>
            <version>${oci.sdk.version}</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The example pins SDK `3.88.0` so modules share the same version; this is a real release, not a claim about the latest release. When integrating into a system, update consistently to a version tested by your project team. [Oracle Java SDK: release 3.88.0](https://github.com/oracle/oci-java-sdk/releases/tag/v3.88.0)

OCI Java SDK 3.x requires applications to select an HTTP client implementation. The Jersey 3 dependency above serves that purpose; adding only the Object Storage and identity modules while omitting the HTTP client can prevent the program from initializing a client. [Oracle: Updates in Version 3 of the OCI SDK for Java](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdk3.htm)

### 5.4. Program Using Workload Identity

The program has two modes: `get` reads an existing object, and `put` attempts to create a marker object with a random name. Under this lesson's policy, `get` must succeed and `put` must be denied.

~~~java
package vn.example.oke;

import com.oracle.bmc.ClientConfiguration;
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.okeworkloadidentity.OkeWorkloadIdentityAuthenticationDetailsProvider;
import com.oracle.bmc.model.BmcException;
import com.oracle.bmc.objectstorage.ObjectStorageClient;
import com.oracle.bmc.objectstorage.requests.GetObjectRequest;
import com.oracle.bmc.objectstorage.requests.PutObjectRequest;
import com.oracle.bmc.objectstorage.responses.GetObjectResponse;
import com.oracle.bmc.objectstorage.responses.PutObjectResponse;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public final class ObjectAccessProbe {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        String regionId = requiredEnv("OCI_REGION");
        String storageNamespace = requiredEnv("OBJECT_STORAGE_NAMESPACE");
        String bucket = requiredEnv("BUCKET_NAME");
        String objectName = requiredEnv("OBJECT_NAME");
        String mode = System.getenv().getOrDefault("MODE", "get");
        if (!mode.equals("get") && !mode.equals("put")) {
            throw new IllegalArgumentException("MODE must be get or put");
        }

        int exitCode = 0;
        try {
            var provider = new OkeWorkloadIdentityAuthenticationDetailsProvider
                    .OkeWorkloadIdentityAuthenticationDetailsProviderBuilder()
                    .build();

            var config = ClientConfiguration.builder()
                    .connectionTimeoutMillis(5_000)
                    .readTimeoutMillis(30_000)
                    .build();

            try (ObjectStorageClient client = ObjectStorageClient.builder()
                    .region(Region.fromRegionId(regionId))
                    .configuration(config)
                    .build(provider)) {
                if (mode.equals("get")) {
                    GetObjectResponse response = client.getObject(
                            GetObjectRequest.builder()
                                    .namespaceName(storageNamespace)
                                    .bucketName(bucket)
                                    .objectName(objectName)
                                    .build());

                    try (InputStream input = response.getInputStream()) {
                        long bytes = input.transferTo(OutputStream.nullOutputStream());
                        System.out.printf("GET_OK bytes=%d requestId=%s%n",
                                bytes, response.getOpcRequestId());
                    }
                } else {
                    String probeName = "identity-probe-" + UUID.randomUUID() + ".txt";
                    byte[] content = "permission-probe".getBytes(StandardCharsets.UTF_8);

                    try (var body = new ByteArrayInputStream(content)) {
                        PutObjectResponse response = client.putObject(
                                PutObjectRequest.builder()
                                        .namespaceName(storageNamespace)
                                        .bucketName(bucket)
                                        .objectName(probeName)
                                        .ifNoneMatch("*")
                                        .contentLength((long) content.length)
                                        .putObjectBody(body)
                                        .build());
                        System.out.printf("PUT_UNEXPECTED_SUCCESS object=%s requestId=%s%n",
                                probeName, response.getOpcRequestId());
                    }
                }
            }
        } catch (BmcException error) {
            System.err.printf("OCI_ERROR status=%d code=%s requestId=%s%n",
                    error.getStatusCode(),
                    error.getServiceCode(),
                    error.getOpcRequestId());
            exitCode = 2;
        }

        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }
}
~~~

The application streams data and counts bytes without logging object contents. `put` mode uses a random name with a no-overwrite condition; if the actual policy grants broader permissions than expected, it leaves behind a marker object that an administrator should delete after investigating.

Do not add fallback to user keys or instance principals in this lab. If a fallback exists, a single successful read is not enough to prove workload identity is configured properly.

### 5.5. Packaging the Image

Create `Dockerfile` in the lab project:

~~~dockerfile
FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
COPY src ./src
RUN mvn -B -q clean package dependency:copy-dependencies -DincludeScope=runtime

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/target/classes /app/classes
COPY --from=build /build/target/dependency /app/lib
USER 10001:10001
ENTRYPOINT ["java", "-cp", "/app/classes:/app/lib/*", "vn.example.oke.ObjectAccessProbe"]
~~~

Keep dependencies as separate JARs so service provider declarations for the HTTP client are not lost during fat-JAR merging.

Build and push the image; replace the sample path with a registry the cluster can pull from:

~~~bash
docker build -t <REGISTRY>/<REPOSITORY>:<TAG> .
docker push <REGISTRY>/<REPOSITORY>:<TAG>
~~~

Registry login and image pull permissions are a separate step. An application using workload identity to read objects does not automatically configure image pull permissions for kubelet.

### 5.6. Assigning the ServiceAccount to the Job

Contents of `workload-job.yaml`; replace all values inside `<...>` before running:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: oke-object-reader
  namespace: reporting
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 180
  template:
    metadata:
      labels:
        app: oke-object-access-probe
    spec:
      serviceAccountName: report-reader
      automountServiceAccountToken: true
      restartPolicy: Never
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: probe
          image: <REGISTRY>/<REPOSITORY>:<TAG>
          imagePullPolicy: IfNotPresent
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          env:
            - name: OCI_REGION
              value: "<OCI_REGION>"
            - name: OBJECT_STORAGE_NAMESPACE
              value: "<OBJECT_STORAGE_NAMESPACE>"
            - name: BUCKET_NAME
              value: "oke-report-input"
            - name: OBJECT_NAME
              value: "samples/orders.csv"
            - name: MODE
              value: "get"
~~~

For a Job, the path to watch is `spec.template.spec.serviceAccountName`. Placing the field under metadata or at `Job.spec` level will not assign the identity to the Pod.

If using a private repository requiring `imagePullSecrets`, add the corresponding field under `spec.template.spec` per your prepared configuration. Do not confuse image pull errors with OCI SDK call errors.

~~~bash
kubectl apply -f workload-job.yaml
kubectl wait -n reporting --for=condition=complete job/oke-object-reader --timeout=180s
kubectl logs -n reporting job/oke-object-reader
~~~

Illustrative output:

~~~text
GET_OK bytes=128 requestId=<request-id>
~~~

The byte count depends on the uploaded data. This log is the expected output for reference, not a transcript of an OCI run in documentation.

## 6. Proving Both Granted Access and Permission Boundaries

A single successful read only confirms the permitted case. You must also run requests that the design is supposed to deny. Keep the image, data, and network configuration identical between runs to avoid misattributing causes.

### 6.1. Change the ServiceAccount While Keeping the Target Resource

Create a new Job from the placeholder-substituted manifest in section 5:

~~~bash
kubectl create --dry-run=client -f workload-job.yaml -o json \
  | jq '.metadata.name = "oke-object-denied-sa" | .spec.template.spec.serviceAccountName = "report-untrusted"' \
  | kubectl apply -f -

kubectl wait -n reporting --for=condition=failed job/oke-object-denied-sa --timeout=180s
kubectl logs -n reporting job/oke-object-denied-sa
~~~

The expected result is that the OCI request is denied when using `report-untrusted`. A `Failed` Job caused by image pull failure, OOM, network error, or deadline expiration **does not prove** IAM blocked the right principal.

If the Job still reads the object, re-check the actual ServiceAccount on the Pod, whether the bucket is still private, and whether other policies grant access to this principal. Having no authentication fallback in the sample program narrows down the investigation.

### 6.2. Keep the Right ServiceAccount but Attempt a Write

Switch `MODE` to `put` and give the Job a different name:

~~~bash
kubectl create --dry-run=client -f workload-job.yaml -o json \
  | jq '.metadata.name = "oke-object-denied-write" | .spec.template.spec.containers[0].env |= map(if .name == "MODE" then .value = "put" else . end)' \
  | kubectl apply -f -

kubectl wait -n reporting --for=condition=failed job/oke-object-denied-write --timeout=180s
kubectl logs -n reporting job/oke-object-denied-write
~~~

An error from OCI matching insufficient write permissions is the expected outcome. If `PUT_UNEXPECTED_SUCCESS` appears, record the marker object name and request ID, audit broader policies, and ask an administrator to delete that object. Do not broaden policies just to make a negative test Job turn `Complete`.

### 6.3. Acceptance Matrix for the Lab

| Scenario | Expected Outcome | What Is Verified |
| --- | --- | --- |
| Right cluster, namespace, ServiceAccount; read existing object in granted bucket | `GET_OK` | Auth path, networking, and read permission all work together |
| Same resource but using `report-untrusted` | OCI denies access | ServiceAccount condition is effective |
| `report-reader` attempts to create a new object in the same bucket | OCI denies write | Read permission is not interpreted as write permission |
| `report-reader` reads an existing object in a second ungranted lab bucket | OCI denies access | Target resource restriction is effective |
| Read a non-existent object | May receive a not-found error | Do not use this result to conclude permissions are right or wrong |

Perform the second-bucket test only if an administrator prepared a second private bucket and reference object in the same compartment. Replace `BUCKET_NAME` and `OBJECT_NAME` in a new Job copy; do not use a random bucket name and treat every 404 as authorization proof.

There is no need to create an extra cluster just for this lesson's negative tests. In systems that already have multiple environments, cluster OCID enforcement can be verified through your organization's integration test workflow.

## 7. Accessing Resources in a Different Compartment

The main exercise intentionally puts cluster and bucket in the same compartment to clarify the baseline flow. In real systems, the cluster may belong to a platform compartment while the bucket belongs to a data compartment.

This case requires configuring a **workload mapping** per OKE's cross-compartment access guide, alongside the service policy. The mapping binds a cluster namespace to a target compartment; the ServiceAccount condition in the policy still provides fine-grained authorization. Do not merely swap the compartment OCID in the `Allow` statement and skip the mapping step.

For example, the platform team is assigned to manage mappings. An IAM administrator places these statements at an appropriately scoped location:

~~~text
Allow group id <PLATFORM_GROUP_OCID> to manage cluster-workload-mappings in compartment id <CLUSTER_COMPARTMENT_OCID>

Allow group id <PLATFORM_GROUP_OCID> to {CLUSTER_WORKLOAD_COMPARTMENT_BIND, CLUSTER_WORKLOAD_COMPARTMENT_UNBIND} in compartment id <DATA_COMPARTMENT_OCID>
~~~

Permission to manage mappings and bind/unbind compartments is an operator permission, not an application permission needed to call `GetObject`. [Oracle: Kubernetes Engine policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/contengpolicyreference.htm)

An authorized operator runs on the admin host:

~~~bash
oci ce workload-mapping create \
  --cluster-id <CLUSTER_OCID> \
  --namespace reporting \
  --mapped-compartment-id <DATA_COMPARTMENT_OCID>
~~~

The three parameters specify the cluster, namespace, and mapped compartment. [Oracle CLI: workload-mapping create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/workload-mapping/create.html)

Next, the data owner grants an object-read policy in `<DATA_COMPARTMENT_OCID>`, still keeping the cluster OCID, namespace, ServiceAccount, and target bucket as in section 4. Because a mapping applies at the namespace level, assess impact on other workloads in that namespace before creating or modifying a mapping.

If a mapping already exists, inspect current configuration and management permissions before adjusting. Managing mappings in the same infrastructure change pipeline as policies prevents situations where a policy moves to a new compartment while the binding remains on the old config. [Oracle: cross-compartment resource access procedure](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

## 8. Networking: IAM Permissions Do Not Create Connectivity

For Pods running in a private subnet, Object Storage can still be reached through the VCN's service gateway. Routes and security rules must permit the path to the Oracle Services Network in the region. A service gateway serves only supported services; Internet access to download dependencies or reach services outside that scope requires a different network path. [Oracle: Access to Oracle Services — Service Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm)

When checking networking, separate two hops:

| Hop | What to Verify |
| --- | --- |
| Pod to OKE authentication flow | Cluster environment supports identity; token is mounted; connection to auth endpoint per OKE/SDK config is not blocked |
| Pod to Object Storage | DNS resolves endpoint; routes are right; HTTPS egress is permitted; TLS trusts the certificate |

In CNIs with dedicated Pod networking, inspect the exact subnet, route table, and NSGs involved in the Pod's path; do not assume every packet follows the node subnet's configuration. Also check NetworkPolicies or proxies/sidecars if the application uses them.

A completely accurate IAM policy still cannot fix a DNS timeout. A completely accurate route also does not let `report-untrusted` read the bucket. Therefore, never add `manage all-resources` to troubleshoot socket or TLS errors.

Image pulling is yet another flow: it happens before the Java program starts. If a Pod is in `ImagePullBackOff`, fix the registry, pull permissions, and image pull network path before investigating workload identity inside the program.

## 9. Extending the Same Identity to Other OCI Services

Workload identity solves authentication. Each service still has its own resource types, permissions, and endpoints. When adding a new requirement, list the APIs the application actually calls and cross-reference that service's policy reference.

### 9.1. Reading a Secret to Connect to a Database

If the application needs to fetch a database password from OCI Secret Management, it can use the same provider to build a Secrets service client. The illustrative policy below targets a single secret in a compartment within the configured scope:

~~~text
Allow any-user to read secret-bundles in compartment id <SECRET_COMPARTMENT_OCID> where all {
  request.principal.type = 'workload',
  request.principal.cluster_id = '<CLUSTER_OCID>',
  request.principal.namespace = 'reporting',
  request.principal.service_account = 'report-reader',
  target.secret.id = '<SECRET_OCID>'
}
~~~

`GetSecretBundle` requires permission to read secret bundles. `read secrets` is for secret metadata and does not substitute for permission to retrieve bundle contents. [Oracle: Vault, Key Management, and Secret Management policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/keypolicyreference.htm)

If the secret is in a different compartment from the cluster, handle the mapping first as in section 7. Do not write decrypted secrets into logs, images, or Git. Successfully retrieving a secret also does not create permissions inside the database: the application must still connect to the DB using an appropriate authentication mechanism and an account with the required SQL privileges.

There are two distinct flows to design separately: calling OCI APIs to manage database resources, and connecting to the database to run queries. Workload identity does not automatically authenticate every JDBC connection or grant table access.

### 9.2. Differentiating Permissions by Application Component

A reporting system might split:

| Component | Recommended ServiceAccount | Business Scope |
| --- | --- | --- |
| Input reader | `report-reader` | Read source data |
| Output writer | `report-writer` | Write to designated output location |
| DB config fetcher | `report-db-client` | Read only the needed secret |

This is an illustrative design. Do not copy the bucket-read policy verbatim to the writer component; map write APIs, create/overwrite permissions, and target resources anew.

## 10. Monitoring and Request Correlation

Application logs should suffice to answer: which operation failed, when, with what HTTP/service code, and with what request ID. You can add environment name, namespace, and ServiceAccount from deployment configuration; self-logged labels only aid lookup and do not replace system-verified identity.

For the lab, retain:

- Job/Pod names and execution timestamps.
- `get` or `put` mode, along with related lab resources.
- `requestId` returned from OCI if present.
- Comparison results against the permission matrix.

**OCI Audit does not record object-level Object Storage events such as `GetObject`**; Audit documentation states Object Storage support is at the bucket level. Use Audit to inspect supported management changes, rather than expecting to find every object read there. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm)

To track object read/write operations, enable bucket **Read Access Events** and **Write Access Events** via OCI Logging as needed. Read logs cover GET/LIST/HEAD operations; write logs cover PUT/POST/DELETE. Log delivery is best effort, so do not treat the immediate absence of a record as sole proof a request never happened. [Oracle: Logging details for Object Storage](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/details_for_object_storage.htm)

Protect log read access and choose retention per operational requirements. Avoid enabling HTTP wire logging that captures Authorization headers or printing tokens for identity debugging. For multi-replica applications, track authentication error rates and OCI call latencies to spot regressions after rollouts, scaling, or network changes.

## 11. Symptom-Based Troubleshooting

Start with Pod status and the actual deployed configuration:

~~~bash
kubectl get pods -n reporting -l app=oke-object-access-probe -o wide
kubectl describe job -n reporting oke-object-reader
kubectl describe pod -n reporting -l job-name=oke-object-reader
kubectl get pods -n reporting -l job-name=oke-object-reader \
  -o custom-columns=NAME:.metadata.name,SA:.spec.serviceAccountName,PHASE:.status.phase
kubectl logs -n reporting job/oke-object-reader
~~~

| Symptom | Check First | Targeted Remediation |
| --- | --- | --- |
| `ImagePullBackOff` | Registry, image tag/digest, pull secret, and image pull connectivity | Fix image pull path; do not jump to conclusions about in-app identity |
| Provider fails to initialize | Cluster type, identity dependency, token mount, and SDK environment | Run on enhanced cluster; use compatible provider and dependencies |
| HTTP client implementation not found | Is Jersey/Jersey 3 dependency on the runtime classpath | Add compatible implementation and preserve service provider metadata when packaging |
| Authentication error or 401 | Token, active provider, path to auth flow, and system clock | Verify auth environment; do not "fix" with broader resource permissions |
| `NotAuthorizedOrNotFound`, 403, or 404 from service | Identity tuple, real bucket/object, region, policy, and mapping | Cross-check every condition and use an object confirmed by admin to exist |
| DNS timeout, connect timeout | DNS, routes, NSGs/security lists, NetworkPolicy, proxy | Inspect the corresponding network hop |
| TLS certificate error | Trust store, proxy, and endpoint certificate | Fix trust chain; keep TLS verification enabled |
| Read succeeds, write denied | Verb/resource type and write API | If workload is read-only, this is expected; if write is needed, design dedicated permissions |
| Job hits `DeadlineExceeded` | Retries, network latency, and build/startup duration | Separate time budget exhaustion from IAM deny |
| Wrong-ServiceAccount test still succeeds | ServiceAccount in Pod and all effective policies | Find leftover permissions or misconfigured deployment before sign-off |

Do not use `kubectl auth can-i` to determine Object Storage permissions: that command queries Kubernetes authorization. It is useful when investigating permissions to create Jobs, read logs, or modify Kubernetes resources.

For token mounts, check the existence and readability of the file at the path used by the provider without copying token contents to the terminal. When needing to re-run a Job after editing configuration, create a new Job name or delete the old lab Job and recreate it; Job Pod templates have fields that cannot be mutated in place.

## 12. Permission Lifecycle Governance and Availability

### 12.1. Protecting ServiceAccount Usage

Under this lesson's model, Pods carrying `report-reader` can exercise the granted read permissions. Therefore, permission to create Pods/Jobs/Deployments in a namespace or edit pod templates is part of the surface granting access to OCI data.

Restrict which users and pipelines can deploy into the `reporting` namespace. If you need to constrain `serviceAccountName`, use a platform-appropriate admission policy; a plain RoleBinding does not fully express restricting which ServiceAccount can be chosen across pod templates. Also review Pod `exec` permissions and permissions to request ServiceAccount tokens.

Someone permitted only to deploy an application should not by default have permission to edit IAM policies or workload mappings. Separating these duties keeps data-boundary reviews clearer.

### 12.2. Repeatable Deployments and Changes

In automated infrastructure pipelines, manage related values together: cluster OCID, namespace, ServiceAccount, target compartment, bucket, and policies. Keep application manifests and IAM aligned under version control, without placing session credentials in source repositories.

When failing over to a recovery cluster, the new cluster OCID must be accounted for in permission design. Matching namespace and ServiceAccount names alone will not make the old policy apply to the new cluster. Prepare policies/mappings and read tests before shifting traffic; explicitly time-box any window where two clusters hold concurrent permissions.

For long-running Java services, verify continued OCI calls across token rotation cycles in integration tests. This lesson's short Job only illustrates access and permission boundaries at runtime.

### 12.3. Revoking Access on Decommission or Incident

Revocation procedures should align with the cause:

1. Stop or isolate the problematic workload to prevent new requests from that process.
2. Narrow or delete IAM statements granting permissions to the affected identity.
3. Check workload mappings and shared ServiceAccounts before modifying or deleting them.
4. Re-verify from a fresh process, accounting for policy propagation time and cached credentials.
5. Audit logs and handle accessed data or unexpected marker objects created.

Do not take deleting a single Pod as sole proof that all permissions are revoked: controllers may spin up replacement Pods with the same ServiceAccount, and other replicas may still exist.

## 13. Cost and Lab Resource Cleanup

Workload identity does not make consumed resources free. In this lab, factors to track include the enhanced cluster, worker nodes or node type used, Object Storage capacity and requests, stored logs, registry, and data transfer.

Use small objects, limit Job retries, and keep `backoffLimit: 0` while verifying permission errors to avoid generating noisy repeated requests. In production, design bounded retries by error type; endlessly retrying IAM errors will not create permissions.

After saving lab evidence, delete the exact three Jobs and two ServiceAccounts created:

~~~bash
kubectl delete job -n reporting \
  oke-object-reader oke-object-denied-sa oke-object-denied-write \
  --ignore-not-found

kubectl delete serviceaccount -n reporting \
  report-reader report-untrusted \
  --ignore-not-found
~~~

If you created an extra Job to test a second bucket, delete that Job as well. Do not delete the entire namespace if it still contains other workloads.

Administrators remove lab-specific IAM statements, delete lab-specific mappings if any after checking impact, clean up any marker objects if a write test unexpectedly succeeded, and then clean up images, buckets, or infrastructure created solely for the lesson. In shared clusters, clean up application resources within your assigned scope.

A deployment meeting this lesson's goals provides clear evidence of reading required data, denying out-of-scope identities/operations, tracing errors via request IDs, and revoking permissions through governance procedures.
