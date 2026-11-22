# Bài thực hành quản lý Object Storage bằng CLI và Java SDK

## 1. Mục tiêu và tình huống thực hành

Trong chương **Thực hành nền tảng OCI** của module **CLOUD_PROVIDERS_ORACLE**, bài này triển khai một quy trình lưu trữ tệp cho ứng dụng Java trên Oracle Cloud Infrastructure. Bạn dùng OCI CLI để chuẩn bị bucket và dữ liệu, sau đó dùng Java SDK để thao tác trên chính các tài nguyên đó.

Tình huống: một ứng dụng cần lưu tệp văn bản và báo cáo CSV trong bucket riêng tư. Nhóm vận hành dùng CLI để kiểm tra; ứng dụng dùng SDK để tải lên, liệt kê, tải xuống và xóa. Hai công cụ phải dùng cùng danh tính, region, namespace và bucket để kết quả có thể đối chiếu.

Sau khi hoàn thành, bạn có thể:

- Phân biệt tenancy, compartment, Object Storage namespace, bucket và object name.
- Thiết lập xác thực API key và giải thích quyền IAM cần cho bài lab.
- Tạo bucket riêng tư; thao tác object, metadata và ETag bằng CLI.
- Tích hợp OCI Java SDK 3.x với Maven và một HTTP client được khai báo rõ ràng.
- Liệt kê đủ các trang, đóng luồng dữ liệu, kiểm tra nội dung tải xuống và xử lý lỗi có request ID.
- Dọn tài nguyên, giải thích các yếu tố ảnh hưởng chi phí và giới hạn bảo vệ dữ liệu của cấu hình lab.

Thời lượng gợi ý: **90–120 phút**, chưa tính thời gian cài công cụ và cấp quyền. Bài lab chỉ tạo một bucket cùng ba object nhỏ trong một region. VCN, Compute và dịch vụ cơ sở dữ liệu Oracle là ngữ cảnh triển khai của module; bạn không cần tạo những tài nguyên đó để làm bài này.

## 2. Mô hình tài nguyên và các giá trị cần thống nhất

~~~mermaid
flowchart LR
    CLI["OCI CLI"] --> AUTH["API signing key và IAM"]
    JAVA["Ứng dụng Java"] --> AUTH
    AUTH --> OS["Object Storage tại region đã chọn"]
    OS --> NS["Namespace của tenancy"]
    NS --> B["Bucket riêng tư"]
    C["Compartment dành cho lab"] -. "chứa bucket, là phạm vi IAM" .-> B
    B --> O1["Object do CLI tải lên"]
    B --> O2["Object do Java tải lên"]
~~~

Namespace không phải một compartment con. Sơ đồ thể hiện quan hệ định địa chỉ và quan hệ quản lý riêng: bucket thuộc một compartment, đồng thời được truy cập qua namespace và endpoint của region.

| Thành phần | Vai trò trong bài |
| --- | --- |
| Tenancy OCID | Định danh tenancy trong cấu hình xác thực |
| User OCID, fingerprint, private key | Danh tính và vật liệu ký yêu cầu API |
| Region | Chọn endpoint và nơi tạo bucket, ví dụ `ap-singapore-1` |
| Compartment OCID | Nơi tạo bucket; IAM dùng phạm vi compartment để giới hạn quyền |
| Namespace | Chuỗi do OCI cấp; không tự suy ra từ tenancy name hoặc tenancy OCID |
| Bucket name | Tên bucket dành riêng cho lần chạy lab |
| Object name | Toàn bộ tên, ví dụ `labs/run-01/cli/hello.txt` |
| ETag | Giá trị nhận dạng trạng thái tài nguyên để dùng trong điều kiện đồng thời |

Object Storage là dịch vụ theo region. Namespace name của một tenancy giống nhau giữa các region, nhưng việc tìm bucket vẫn phụ thuộc region đang gọi. Với bucket theo namespace dùng trong bài, tên bucket phải duy nhất trong namespace tại region tương ứng. Nguồn: [Tổng quan Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm).

Dấu `/` trong object name giúp tổ chức theo prefix; nó không tạo cây thư mục có hành vi như hệ thống tệp POSIX. Muốn lấy `labs/run-01/cli/hello.txt`, phải truyền đủ chuỗi đó, bao gồm chữ hoa, chữ thường và dấu phân cách.

## 3. Chuẩn bị môi trường và quyền IAM

### 3.1. Công cụ và giới hạn của môi trường mẫu

Các lệnh dưới đây dùng **Bash trên Linux hoặc WSL2**, cùng các công cụ `sha256sum` và `cmp`. Nếu làm trên Windows, hãy cài OCI CLI, JDK và Maven trong cùng môi trường WSL2; đường dẫn private key trong config cũng phải hợp lệ ở WSL2. Không dán nguyên cú pháp Bash vào PowerShell.

Chuẩn bị:

- OCI CLI 3.x đã cài đặt.
- JDK 17 và Maven 3.9.x.
- Kết nối HTTPS đến endpoint Object Storage của region đã chọn và kho Maven.
- Một compartment sandbox, ví dụ `OciObjectLab`.
- Một user thuộc nhóm chỉ dùng cho lab, ví dụ `OciObjectLabUsers`.
- Một API signing key đã đăng ký public key cho user đó.

Kiểm tra công cụ:

~~~bash
oci --version
java -version
mvn -version
~~~

Đối chiếu kết quả `mvn -version` để chắc Maven thực sự dùng JDK 17. API signing key dùng cho OCI API khác với SSH key đăng nhập Compute và khác với Customer Secret Key dùng cho giao diện tương thích S3.

### 3.2. Policy phục vụ bài lab

Quản trị viên chuẩn bị compartment, nhóm, thành viên nhóm và policy trước khi người học chạy lệnh. Ví dụ với identity domain `Default` và compartment nằm ngay dưới tenancy:

~~~text
Allow group Default/OciObjectLabUsers to read objectstorage-namespaces in tenancy
Allow group Default/OciObjectLabUsers to manage buckets in compartment OciObjectLab
Allow group Default/OciObjectLabUsers to manage objects in compartment OciObjectLab
~~~

Thay đúng identity domain, group và compartment của môi trường. Nếu compartment lồng nhau, dùng cách định danh compartment phù hợp với cây compartment của tenancy. Đặt policy ở tenancy hoặc cấp cha phù hợp với phạm vi được cấp; người học không cần quyền tự sửa IAM.

Hai dòng `manage` cho phép tạo, kiểm tra và dọn tài nguyên trong compartment sandbox. Đây là bộ quyền phục vụ trọn vòng đời bài lab, rộng hơn quyền ứng dụng chỉ tải hoặc đọc một số object. Không cấp `manage all-resources in tenancy` để giải quyết lỗi quyền.

Quyền bucket và quyền object là hai lớp riêng. Có thể xem hoặc tạo bucket không đồng nghĩa được đọc nội dung object. Riêng thao tác tạo object mới cần `OBJECT_CREATE`; chỉ cấp `use objects` không đủ cho mọi lần `PutObject`. Đối chiếu [bảng quyền Object Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm) và [cú pháp policy theo identity domain](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm).

Khi đưa vào ứng dụng thực tế, tách quyền quản trị bucket khỏi quyền xử lý dữ liệu. Có thể giới hạn policy object vào một bucket bằng điều kiện `target.bucket.name` và chọn các permission phù hợp. Policy hẹp chỉ có tác dụng giới hạn quyền nếu danh tính không đồng thời nhận quyền rộng hơn từ nhóm hoặc policy khác.

### 3.3. Cấu hình API key dùng chung cho CLI và SDK

Tạo hoặc bổ sung profile `LAB` trong `~/.oci/config`. Các giá trị sau là chỗ giữ chỗ, phải thay bằng thông tin thật của môi trường:

~~~ini
[LAB]
user=ocid1.user.oc1..REPLACE_WITH_USER_OCID
fingerprint=REPLACE_WITH_REGISTERED_PUBLIC_KEY_FINGERPRINT
tenancy=ocid1.tenancy.oc1..REPLACE_WITH_TENANCY_OCID
region=ap-singapore-1
key_file=/home/your-user/.oci/oci_api_key.pem
~~~

Private key phải tương ứng public key đã đăng ký cho đúng user. Nếu key được mã hóa, cấu hình cơ chế cung cấp passphrase tại runtime tương ứng cho cả CLI và Java; mã mẫu bên dưới không có bước hỏi passphrase tương tác. Không chép private key, passphrase hoặc nội dung config vào mã nguồn, object hay báo cáo lab. Tham khảo [cấu hình SDK và CLI](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm).

Trên Linux/WSL2, giới hạn quyền đọc tệp theo tài khoản đang dùng:

~~~bash
chmod 700 "$HOME/.oci"
chmod 600 "$HOME/.oci/config"
chmod 600 "$HOME/.oci/oci_api_key.pem"
~~~

Nếu key nằm ở đường dẫn khác, thay đường dẫn trong lệnh cuối. Với WSL2, nên lưu key trong hệ thống tệp Linux của WSL để quản lý quyền tệp nhất quán.

## 4. Khởi tạo phiên làm việc và xác minh kết nối

Giữ cùng một phiên Bash cho toàn bộ bài. Sửa region và compartment OCID trước khi chạy:

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

Hàm `oci_lab` cố định config, profile, kiểu xác thực và region cho từng lệnh. Java sẽ đọc các biến `OCI_LAB_*` tương ứng; đây là quy ước của chương trình lab, không phải bộ biến tự động được SDK nhận biết.

`os ns get` thành công chứng minh yêu cầu lấy namespace đã được xác thực và xử lý. Nó chưa chứng minh bạn có quyền tạo bucket, tải lên hoặc xóa object. Nếu bước này lỗi, giải quyết xác thực và kết nối trước khi đi tiếp. Cách dùng CLI và lựa chọn kiểu xác thực được mô tả trong [Using the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliusing.htm).

## 5. Phần A — Quản lý bucket và object bằng OCI CLI

### 5.1. Tạo và kiểm tra bucket riêng tư

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

Xác nhận kết quả:

| Thuộc tính | Giá trị mong đợi |
| --- | --- |
| `name` | Bằng `OCI_LAB_BUCKET` |
| `compartment-id` | Bằng compartment OCID đã chọn |
| `public-access-type` | `NoPublicAccess` |
| `storage-tier` | `Standard` |
| `versioning` | `Disabled` |

Bài chọn Standard để đọc dữ liệu ngay trong buổi thực hành và tắt versioning để quy trình dọn tài nguyên chỉ xử lý các object hiện tại. Tham số và giá trị hợp lệ nằm trong [CLI bucket create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/create.html).

Bucket riêng tư vẫn được truy cập qua endpoint dịch vụ có thể định tuyến công khai; `NoPublicAccess` kiểm soát truy cập ẩn danh, không tự tạo đường mạng riêng. Trong mô hình Compute ở private subnet, có thể thiết kế đường đến Object Storage qua service gateway; kết nối mạng và quyền IAM vẫn phải cùng hợp lệ.

### 5.2. Tạo dữ liệu mẫu và tải lên hai object

~~~bash
cat > data/hello.txt <<'EOF'
Xin chào OCI Object Storage.
Tệp này được dùng để đối chiếu dữ liệu giữa CLI và Java SDK.
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

`--name` đặt đầy đủ object name, độc lập với đường dẫn tệp cục bộ. `--no-overwrite` tránh ghi đè ngoài ý muốn khi chạy lại lệnh; hãy kiểm tra kết quả vì một lần bỏ qua object đã tồn tại không phải một lần tải lên mới. `--no-multipart` giữ đường đi đơn giản cho dữ liệu vài KB. Metadata mô tả dữ liệu, không thay thế nội dung tệp hoặc cơ chế kiểm soát truy cập. Nguồn: [CLI object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

### 5.3. Liệt kê đúng prefix và đọc metadata

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

Lúc này phải có **hai object** thuộc prefix của lần chạy. `--all` yêu cầu CLI lấy toàn bộ trang kết quả; không kết hợp nó với `--limit`. `head` lấy thông tin object mà không tải phần nội dung. Xem [CLI object list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/list.html) và [CLI object head](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/head.html).

Giữ nguyên ETag do dịch vụ trả về khi dùng cho điều kiện `If-Match`. Không tự bỏ ký tự, tái tạo ETag từ nội dung hoặc coi ETag là SHA-256 của tệp.

### 5.4. Tải xuống và kiểm tra nội dung

~~~bash
oci_lab os object get \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_CLI_TEXT_KEY" \
  --file downloads/hello-cli.txt

cmp data/hello.txt downloads/hello-cli.txt
sha256sum data/hello.txt downloads/hello-cli.txt
~~~

`cmp` trả mã `0` và hai SHA-256 giống nhau là bằng chứng dữ liệu tải xuống trùng dữ liệu gốc. Dòng lệnh thành công hoặc kích thước bằng nhau chưa đủ để chứng minh điều đó. `--file` là tệp đích trên máy đang chạy CLI, còn `--name` là object name trên OCI. Tham khảo [CLI object get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/get.html).

## 6. Phần B — Xây dựng chương trình Java SDK

### 6.1. Cấu trúc và dependency Maven

Từ thư mục làm việc đã tạo, lưu hai tệp sau:

~~~text
oci-object-lab/<run-id>/
├── pom.xml
├── src/main/java/lab/ObjectStorageLab.java
├── data/
└── downloads/
~~~

Nội dung `pom.xml`:

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

Bản SDK `3.102.0` được cố định cho mẫu này và có [bản phát hành chính thức của Oracle](https://github.com/oracle/oci-java-sdk/releases/tag/v3.102.0). Khi nâng phiên bản, nâng đồng bộ thông qua BOM và kiểm tra lại tương thích.

SDK 3.x yêu cầu ứng dụng chủ động chọn HTTP client. Mẫu chọn Jersey 3; thiếu dependency này có thể làm chương trình không khởi tạo được HTTP provider. Xem [hướng dẫn Java SDK](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm) và [ghi chú SDK 3.x của Oracle](https://github.com/oracle/oci-java-sdk/blob/v3.102.0/README.md).

### 6.2. Mã nguồn thực hiện bốn thao tác

Lưu nội dung sau vào `src/main/java/lab/ObjectStorageLab.java`:

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

Các quyết định cần hiểu trong mã:

- `put` dùng `ifNoneMatch("*")` để yêu cầu tạo object khi tên chưa tồn tại. Đây là điều kiện phía dịch vụ, khác với việc chỉ kiểm tra tồn tại rồi mới tải lên ở phía ứng dụng.
- Kích thước upload bị giới hạn ở 16 MiB theo chủ đích của mẫu. Với tệp lớn, dùng cơ chế multipart hoặc `UploadManager` sau khi thiết kế cách thử lại và dọn upload chưa hoàn tất.
- Upload không tự retry vì luồng đầu vào trong mẫu không được thiết kế để phát lại tùy ý. Nếu timeout sau khi gửi dữ liệu, phải kiểm tra object trước khi quyết định chạy lại.
- `list` yêu cầu `size` trong `fields` và dùng kích thước trang bằng hai để quan sát phân trang.
- `get` đọc theo stream, đóng stream bằng `try-with-resources` và không chủ động ghi đè tệp đích. Tạo sẵn thư mục cha trước khi chạy.
- `delete` nhận ETag mong đợi để tránh xóa object đã bị tác nhân khác cập nhật.
- `BmcException` được ghi mã trạng thái, service code và request ID rồi ném lại; lời gọi thất bại không bị báo như thành công.

Tham số upload và điều kiện ETag được mô tả tại [PutObjectRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/PutObjectRequest.Builder.html); điều kiện xóa tại [DeleteObjectRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/DeleteObjectRequest.Builder.html). Việc tắt retry dùng [RetryConfiguration](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/retrier/RetryConfiguration.html).

Đặc biệt, `ListObjects` trả mốc trang kế tiếp trong **body** qua `getNextStartWith()`; truyền lại bằng `start(...)`. Không mặc định mọi API liệt kê của OCI đều dùng cùng một header phân trang. Xem [ListObjects](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/model/ListObjects.html) và [ListObjectsRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/ListObjectsRequest.Builder.html).

## 7. Chạy Java và kiểm tra tương tác hai chiều với CLI

### 7.1. Biên dịch và tải lên object thứ ba

~~~bash
mvn -q -DskipTests compile

mvn -q exec:java \
  "-Dexec.args=put $OCI_LAB_JAVA_KEY data/hello.txt"

oci_lab os object head \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --bucket-name "$OCI_LAB_BUCKET" \
  --name "$OCI_LAB_JAVA_KEY"
~~~

Kết quả Java có dòng `PUT` kèm ETag và request ID. CLI phải đọc được object vừa tạo, với metadata thể hiện `writer=java-sdk`. Không yêu cầu request ID của các lệnh khác nhau phải giống nhau.

### 7.2. Java liệt kê đầy đủ dữ liệu do cả hai công cụ tạo

~~~bash
mvn -q exec:java \
  "-Dexec.args=list $OCI_LAB_PREFIX"
~~~

Có ba object thuộc prefix của lần chạy: hai object do CLI tạo và một object do SDK tạo. Với `limit(2)`, quan sát chương trình đi qua các trang cho đến khi hết `nextStartWith`; không dừng sau trang đầu.

Ví dụ hình dạng kết quả, các giá trị trong dấu `<...>` thay đổi theo môi trường:

~~~text
LIST page=1 requestId=<request-id-1>
  name=labs/<run-id>/cli/hello.txt size=<bytes>
  name=labs/<run-id>/cli/metrics.csv size=<bytes>
LIST page=2 requestId=<request-id-2>
  name=labs/<run-id>/java/hello.txt size=<bytes>
~~~

Đây là kết quả minh họa để đối chiếu, không phải log từ một lần triển khai đã chạy sẵn.

### 7.3. Java đọc object của CLI; CLI đọc object của Java

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

Cả bốn SHA-256 phải bằng nhau. Kết quả này xác nhận hai công cụ truy cập cùng dữ liệu, đồng thời kiểm tra đường đọc qua CLI và Java.

Nếu đứt mạng trong khi `Files.copy` đang đọc stream, có thể còn tệp tải xuống dở. Không coi tệp đó là hợp lệ; kiểm tra nội dung, xử lý riêng tệp dở và tải lại vào một đường dẫn mới. Ứng dụng thực tế nên tải vào tệp tạm rồi đổi tên sau khi kiểm tra thành công.

## 8. Thử một lỗi có kiểm soát và hiểu điều kiện đồng thời

Chạy lại thao tác Java `put` với đúng object name đã tồn tại. Đặt trong `if` để lỗi dự kiến không làm `set -e` dừng toàn bộ phiên:

~~~bash
if mvn -q exec:java \
  "-Dexec.args=put $OCI_LAB_JAVA_KEY data/hello.txt"; then
  printf 'Không đạt: lệnh tạo trùng đã thành công ngoài dự kiến.\n'
else
  printf 'Đọc dòng OCI_ERROR; chỉ coi đạt khi status=412 do điều kiện tạo trùng.\n'
fi
~~~

Mẫu có `ifNoneMatch("*")` nên lần tạo trùng phải bị từ chối với HTTP `412` khi object vẫn tồn tại. Một lỗi Maven, mạng hoặc xác thực cũng tạo mã thoát khác không, nhưng không chứng minh điều kiện tạo trùng đã hoạt động. Phải đọc `OCI_ERROR` và đối chiếu đúng nguyên nhân.

Để hiểu thao tác cập nhật mà không mở rộng bài lab thành một ứng dụng khác:

| Ý định | Điều kiện phù hợp | Khi điều kiện không còn đúng |
| --- | --- | --- |
| Chỉ tạo object mới | `If-None-Match: *` | Không thay thế object hiện có |
| Chỉ ghi đè trạng thái đã đọc | `If-Match: <ETag đã đọc>` | Trả lỗi điều kiện thay vì ghi đè trạng thái mới |
| Chỉ xóa trạng thái đã xác nhận | `If-Match: <ETag đã đọc>` | Không xóa object vừa bị cập nhật |

Trong CLI, `object put --if-match` hỗ trợ cập nhật có điều kiện. `--force` chỉ bỏ bước hỏi xác nhận ghi đè của công cụ; nó không thay thế cơ chế kiểm tra ETag ở dịch vụ.

Nếu ứng dụng gặp lỗi điều kiện, đọc lại trạng thái và quyết định theo nghiệp vụ. Không tự động bỏ `If-Match` hoặc `If-None-Match` để ép thao tác thành công.

## 9. Chẩn đoán lỗi theo lớp

| Biểu hiện | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| `401` hoặc lỗi chữ ký | Profile, user OCID, key, fingerprint, thời gian máy | Kiểm tra public key của đúng user và đồng hồ; không đổi IAM ngẫu nhiên |
| `403`, hoặc `404 NotAuthorizedOrNotFound` | Quyền IAM và toàn bộ địa chỉ tài nguyên | Kiểm tra cả quyền lẫn region, namespace, bucket, object name; 404 không luôn có nghĩa tài nguyên không tồn tại |
| Lấy namespace được nhưng upload không được | Policy cho `objects` | Kiểm tra quyền tạo object mới và phạm vi compartment của bucket |
| Java và CLI thấy dữ liệu khác nhau | Bốn giá trị region, namespace, bucket, prefix | In các giá trị không nhạy cảm từ phiên lab để đối chiếu |
| Chỉ thấy hai object trong Java | Mốc `nextStartWith` | Bảo đảm vòng lặp truyền lại `start` và chạy đến hết |
| HTTP provider không khởi tạo được | Dependency HTTP client và phiên bản SDK | Kiểm tra Jersey 3 có mặt, các module dùng cùng BOM |
| `412` | Điều kiện tạo hoặc ETag | Xác định object đã tồn tại hay trạng thái đã đổi; xử lý theo ý định nghiệp vụ |
| `429` hoặc `5xx` | Request ID, tần suất gọi và tình trạng kết nối | Giới hạn số lần thử lại, dùng backoff có jitter và bảo đảm request có thể phát lại |
| Tệp tải xuống bị thiếu hoặc sai hash | Stream, đường dẫn, lần tải dở | Không dùng tệp lỗi; tải lại sau khi xác định nguyên nhân |
| Xóa bucket báo còn dữ liệu | Object khác, version hoặc multipart chưa hoàn tất | Kiểm kê tài nguyên trước; không chuyển ngay sang xóa hàng loạt |

Có thể xem dependency đã giải quyết bằng:

~~~bash
mvn dependency:tree -Dincludes=com.oracle.oci.sdk
~~~

Với lỗi cần điều tra, lưu thời điểm UTC, thao tác, region, bucket, object name, mã lỗi và request ID. Giới hạn việc chia sẻ OCID và đường dẫn nội bộ theo quy định của nhóm. Không đưa private key hoặc toàn bộ log debug chưa rà soát vào báo cáo.

## 10. Chi phí, quan sát và lựa chọn triển khai

### 10.1. Giữ phạm vi chi phí nhỏ

Mẫu chỉ dùng ba object nhỏ và Standard tier. Khi vận hành thực tế, cần theo dõi dung lượng lưu trữ, số lượng yêu cầu, truyền dữ liệu ra ngoài và những tính năng bổ sung được bật. Không giả định bài lab luôn miễn phí dựa vào tên gói tài khoản.

Dùng bucket riêng cho từng lần chạy giúp kiểm kê và dọn tài nguyên rõ ràng. Có thể gắn tag theo chính sách của tổ chức và đặt budget để cảnh báo; cảnh báo budget không phải công tắc tự động dừng mọi khoản chi.

Không bật Archive, lifecycle chuyển tier, replication hoặc retention rule chỉ để hoàn thành bài. Những tính năng đó cần kế hoạch về thời gian truy xuất, quyền dịch vụ, thời hạn giữ dữ liệu và chi phí tương ứng.

### 10.2. Quan sát và tính sẵn sàng

Log trong mã Java giúp nối một thao tác ứng dụng với yêu cầu dịch vụ. Trong OCI Console, mở đúng bucket và xem phần Monitoring để quan sát metrics phù hợp; chờ dữ liệu giám sát cập nhật trước khi kết luận không có hoạt động.

Object Storage cung cấp lưu trữ theo region và không phụ thuộc vòng đời một Compute instance. Điều đó không tự bảo vệ dữ liệu khỏi mọi thao tác xóa hợp lệ hoặc sự cố trên phạm vi region. Với hệ thống sản xuất, cần xác định RPO/RTO rồi lựa chọn versioning, retention, bản sao và replication thích hợp; thử khôi phục dữ liệu là một bước riêng.

Lab tắt versioning để đơn giản hóa việc dọn dẹp. Vì vậy, không dùng cấu hình này làm mẫu bảo vệ dữ liệu quan trọng. Mã mẫu cũng chưa triển khai multipart, tải xuống nguyên tử, thử lại upload có khả năng phát lại hoặc cơ chế khôi phục sau lỗi.

Khi ứng dụng chạy trên OCI Compute, có thể thay API key lưu trên máy bằng instance principal cùng dynamic group và policy tương ứng. Không thể chỉ bỏ config mà giữ nguyên auth provider hiện tại; CLI và Java đều phải được chuyển sang cơ chế principal phù hợp. Không cấp thêm quyền hoặc mở bucket công khai để thay cho việc cấu hình xác thực.

## 11. Xóa object bằng SDK và CLI, sau đó xóa bucket

Chỉ dọn bucket vừa tạo sau khi đã lưu bằng chứng cần thiết. Các lệnh bên dưới giả định versioning vẫn `Disabled` và không có tác nhân khác thêm dữ liệu vào bucket.

### 11.1. Java xóa object đã tạo

Lấy ETag mới nhất từ dịch vụ rồi truyền nguyên giá trị cho Java. Dấu nháy trong `exec.args` giữ ETag thành một đối số:

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

Nếu ETag đã thay đổi giữa `head` và `delete`, điều kiện xóa phải thất bại. Kiểm tra thay đổi trước khi lấy ETag mới và quyết định lại. Không bỏ điều kiện chỉ để xóa cho xong.

### 11.2. CLI xóa hai object còn lại

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

Kết quả đếm phải là `0`. Ở bước này kiểm tra toàn bucket, không chỉ prefix của phiên. `--force` bỏ câu hỏi xác nhận xóa, còn `--if-match` giữ điều kiện trạng thái cho object văn bản. Tham khảo [CLI object delete](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/delete.html).

### 11.3. Xóa bucket rỗng và xác minh

~~~bash
printf 'Sắp xóa bucket lab: %s\n' "$OCI_LAB_BUCKET"

oci_lab os bucket delete \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --name "$OCI_LAB_BUCKET" \
  --force
~~~

Lệnh xóa bucket thông thường yêu cầu bucket đã rỗng. Không dùng `--empty` trong quy trình này vì cần kiểm tra từng tài nguyên còn lại trước khi xóa. Xem [CLI bucket delete](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/delete.html).

Sau khi lệnh thành công, xác minh bucket không còn xuất hiện trong danh sách bucket của đúng compartment và region:

~~~bash
oci_lab os bucket list \
  --namespace-name "$OCI_LAB_NAMESPACE" \
  --compartment-id "$OCI_LAB_COMPARTMENT_OCID" \
  --all \
  --query 'data[].name'
~~~

Nếu bucket không xóa được dù danh sách object hiện tại rỗng, kiểm tra versioning, các phiên bản cũ, upload multipart chưa hoàn tất, retention và các cấu hình liên quan. Không áp dụng quy trình ba object này nguyên trạng cho bucket dùng chung.

Chỉ thu hồi API key hoặc policy nếu chúng được tạo riêng cho phiên lab và đã hết nhu cầu sử dụng. Không xóa khóa, nhóm hay policy dùng chung cho các bài hoặc ứng dụng khác.

## 12. Bằng chứng hoàn thành bài thực hành

| Nội dung kiểm chứng | Bằng chứng cần lưu |
| --- | --- |
| Đúng phạm vi tài nguyên | Region, namespace, bucket và compartment đã sử dụng |
| Bucket riêng tư | Kết quả `bucket get` có `NoPublicAccess` |
| CLI thao tác được dữ liệu | Hai object xuất hiện, metadata đọc được, tải xuống đúng nội dung |
| Java tạo object | Dòng `PUT` và kết quả CLI đọc lại object đó |
| Java liệt kê đủ | Ba object được đọc qua các trang kết quả |
| CLI và Java đọc chéo | Các phép `cmp` thành công và SHA-256 bằng nhau |
| Điều kiện chống tạo trùng | Lỗi `412` đúng ngữ cảnh, dữ liệu cũ vẫn đọc được |
| Xử lý và truy vết lỗi | Có mã lỗi và request ID khi dịch vụ trả lỗi |
| Dọn object và bucket | Toàn bucket về `0` object, xóa bucket thành công và kiểm tra lại danh sách |

Báo cáo chỉ chứa thông tin đã lược bỏ dữ liệu nhạy cảm. Nếu chưa chạy một bước, ghi rõ chưa thực hiện; không thay bằng log minh họa trong bài. Kết quả mong đợi của bài là một quy trình lưu trữ riêng tư có thể lặp lại, kiểm tra được dữ liệu và kết thúc với tài nguyên lab đã được dọn.
