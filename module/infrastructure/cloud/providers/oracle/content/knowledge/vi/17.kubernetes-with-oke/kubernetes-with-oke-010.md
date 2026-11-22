# OKE workload identity và truy cập dịch vụ OCI

Trong chương **Kubernetes với OKE** của module **CLOUD_PROVIDERS_ORACLE**, bài này nối phần Kubernetes với mô hình phân quyền của Oracle Cloud Infrastructure (OCI): một ứng dụng chạy trong Pod cần đọc dữ liệu ở Object Storage, lấy cấu hình bí mật hoặc gọi một dịch vụ OCI mà không phải mang theo API signing key của người dùng.

Mục tiêu là triển khai được quyền truy cập gắn với ứng dụng, hiểu quan hệ giữa tenancy, compartment, Kubernetes ServiceAccount và IAM, đồng thời vận hành được đường mạng, log và vòng đời quyền. Bài thực hành dùng một chương trình Java đọc object đã có trong bucket riêng tư; các phép thử từ chối giúp xác nhận giới hạn quyền.

## 1. Danh tính của workload nằm ở đâu?

Giả sử ứng dụng báo cáo có ba replica, phân bố trên hai worker node. Cả ba Pod cần đọc cùng một bucket, trong khi ứng dụng thanh toán chạy chung node không được phép đọc bucket đó. Nếu cấp quyền theo node, việc phân biệt hai ứng dụng trở nên khó quản lý. Nếu chép khóa OCI vào từng Pod, hệ thống phải bảo vệ và luân chuyển thêm nhiều bản sao thông tin xác thực.

OKE workload identity dùng bộ ba:

~~~text
(cluster OCID, Kubernetes namespace, Kubernetes ServiceAccount)
~~~

Các Pod dùng cùng bộ ba này có chung danh tính workload đối với IAM. Tăng replica hoặc thay Pod không tạo một danh tính IAM riêng cho từng replica. Workload identity yêu cầu **enhanced cluster** và không dùng dynamic group để gom workload. [Oracle: Granting Workloads Access to OCI Resources](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

Ví dụ xuyên suốt bài:

| Thành phần | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| Cluster | `<CLUSTER_OCID>` | Phân biệt cụm production với cụm khác |
| Kubernetes namespace | `reporting` | Ranh giới tổ chức ứng dụng trong cluster |
| ServiceAccount | `report-reader` | Danh tính được gán vào Pod |
| Compartment OCI | `<LAB_COMPARTMENT_OCID>` | Nơi chứa cluster và bucket của bài thực hành |
| Bucket riêng tư | `oke-report-input` | Tài nguyên được cấp quyền đọc |
| Object có sẵn | `samples/orders.csv` | Dữ liệu thử không chứa thông tin nhạy cảm |

**Kubernetes namespace** và **Object Storage namespace** là hai khái niệm khác nhau. Namespace `reporting` chỉ có ý nghĩa trong Kubernetes; Object Storage namespace là tên không gian lưu trữ của tenancy, dùng trong API Object Storage. Không điền tên Kubernetes namespace vào tham số `namespaceName` của OCI SDK.

Một hệ quả thiết kế: hai thành phần có quyền khác nhau cần ServiceAccount khác nhau, ngay cả khi chúng thuộc cùng một ứng dụng nghiệp vụ. Không dùng chung `report-reader` cho mọi Deployment trong namespace rồi kỳ vọng IAM phân biệt dựa trên tên Deployment hay nhãn Pod.

## 2. Ba lớp quyết định một yêu cầu có thành công hay không

Một lệnh đọc object thành công cần đồng thời có:

1. **Danh tính hợp lệ:** chương trình dùng đúng provider, có token ServiceAccount và chạy trong môi trường OKE hỗ trợ.
2. **Quyền hợp lệ:** IAM cho phép đúng principal thực hiện thao tác trên tài nguyên đích.
3. **Kết nối hợp lệ:** Pod đi được đến luồng xác thực và endpoint của dịch vụ, với DNS, TLS và route phù hợp.

Kubernetes RBAC giải quyết quyền với Kubernetes API, chẳng hạn đọc ConfigMap hoặc tạo Job. OCI IAM giải quyết quyền với dịch vụ OCI. Cấp `ClusterRoleBinding` không thay cho policy đọc object; ngược lại, policy Object Storage không cấp quyền đọc Kubernetes Secret. [Kubernetes: Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

| Cách xác thực | Danh tính đại diện | Điểm cần cân nhắc với ứng dụng trong Pod |
| --- | --- | --- |
| API signing key của người dùng | Người dùng IAM sở hữu khóa | Cần lưu khóa, xoay vòng và thu hồi các bản sao |
| Instance principal | Compute instance | Quyền gắn với node; không tự tạo ranh giới theo ứng dụng |
| OKE workload identity | Bộ ba cluster, namespace, ServiceAccount | Phù hợp khi muốn cấp quyền theo workload |
| Kubernetes ServiceAccount token dùng với Kubernetes API | ServiceAccount trong cluster | Token này không tự trở thành quyền OCI chỉ vì đã mount vào Pod |

Bảng trên giúp chọn ranh giới quyền. Workload identity giảm nhu cầu phân phối khóa người dùng, nhưng token vẫn là thông tin xác thực phải được bảo vệ.

## 3. Luồng xác thực qua OCI SDK

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant P as Pod reporting/report-reader
    participant S as OCI SDK trong ứng dụng
    participant I as Hạ tầng xác thực OKE/OCI
    participant O as Object Storage + IAM
    K->>P: Cấp token ServiceAccount cho Pod
    P->>S: Gọi GetObject
    S->>I: Dùng OKE workload identity provider
    I-->>S: Thông tin xác thực phiên
    S->>O: Yêu cầu đã ký tới object đích
    O->>O: Đánh giá IAM policy
    O-->>S: Dữ liệu hoặc lỗi từ chối
~~~

Đây là sơ đồ khái niệm để định vị nơi xảy ra lỗi; ứng dụng để SDK thực hiện giao thức xác thực và ký yêu cầu. Không tự gửi token Kubernetes làm bearer token đến Object Storage.

Trong cấu hình Kubernetes hiện đại, token ServiceAccount được mount bằng projected volume, có thời hạn và được kubelet xoay vòng. Bài thực hành giữ cơ chế mount tiêu chuẩn để provider đọc được token; không tạo Secret token dài hạn bằng tay. [Kubernetes: Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/)

Tạo một `OkeWorkloadIdentityAuthenticationDetailsProvider` dùng lại trong mỗi tiến trình, thay vì tạo provider mới cho từng HTTP request. Với dịch vụ Java chạy lâu dài, có thể quản lý provider và các OCI client như singleton có vòng đời rõ ràng. SDK duy trì cache thông tin xác thực; khởi tạo lặp lại làm tăng số lần lấy token. [Oracle: hướng dẫn dùng provider](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

Ứng dụng vẫn gọi API của dịch vụ qua SDK; workload identity không phải một cách đăng nhập OCI Console. Trong bài này, OCI CLI trên máy quản trị phục vụ việc chuẩn bị tài nguyên, còn yêu cầu trong Pod được ký bởi provider Java.

## 4. Viết IAM policy theo tài nguyên và thao tác cần thiết

### 4.1. Policy chỉ đọc object trong một bucket

Người có quyền quản trị IAM tạo policy ở vị trí có phạm vi bao phủ compartment của bucket. Thay hai placeholder OCID bằng giá trị thật:

~~~text
Allow any-user to read objects in compartment id <LAB_COMPARTMENT_OCID> where all {
  request.principal.type = 'workload',
  request.principal.cluster_id = '<CLUSTER_OCID>',
  request.principal.namespace = 'reporting',
  request.principal.service_account = 'report-reader',
  target.bucket.name = 'oke-report-input'
}
~~~

Mỗi điều kiện có một nhiệm vụ:

| Điều kiện | Ràng buộc cần giữ |
| --- | --- |
| `request.principal.type` | Yêu cầu được xác thực bằng danh tính workload |
| `request.principal.cluster_id` | Đúng cluster đã được phê duyệt |
| `request.principal.namespace` | Đúng namespace của ứng dụng |
| `request.principal.service_account` | Đúng ServiceAccount của thành phần đọc dữ liệu |
| `target.bucket.name` | Đúng bucket đầu vào |

`any-user` là chủ thể trong cú pháp policy có điều kiện. Quyền vẫn phụ thuộc toàn bộ biểu thức `where all`; bucket không vì vậy trở thành public. Khi review, phải kiểm tra cả phần `Allow`, phạm vi compartment và toàn bộ điều kiện, không chỉ nhìn riêng từ `any-user`.

Với Object Storage, `read objects` bao gồm đọc nội dung và các quyền inspect đối tượng, nên không phải chỉ cho phép duy nhất `GetObject`. Nó không cấp quyền tạo bucket hay ghi/xóa object. Điều kiện tên bucket được IAM so sánh không phân biệt hoa thường; tránh thiết kế hai bucket mà ranh giới quyền chỉ khác chữ hoa và chữ thường. [Oracle: Object Storage policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm)

Bài thực hành cung cấp sẵn Object Storage namespace, bucket và object. Chương trình không liệt kê toàn bộ bucket để dò tài nguyên. Cách này giúp phạm vi API trong ví dụ khớp với nhu cầu đọc đầu vào.

### 4.2. Quyền có thể đến từ nhiều policy

Nếu đã có một policy khác cấp rộng hơn cho cùng principal, policy hẹp ở trên không thu hồi phần quyền rộng đó. Khi phép thử ghi vẫn thành công, hãy kiểm tra các policy áp dụng ở tenancy và các compartment liên quan, thay vì chỉ nhìn policy vừa tạo.

Việc bỏ một điều kiện như cluster OCID cũng làm thay đổi mô hình tin cậy. Một cluster thử nghiệm có thể dùng cùng tên namespace và ServiceAccount với production; giữ cluster OCID giúp tách hai môi trường trong policy này.

## 5. Thực hành: Java Job đọc Object Storage

### 5.1. Chuẩn bị và quy ước

Dùng môi trường lab với các điều kiện sau:

- Một OKE enhanced cluster hoạt động; người triển khai có kubeconfig của chính mình và quyền tạo Namespace, ServiceAccount, Job trong phạm vi lab.
- Cluster và bucket nằm **cùng một compartment OCI** trong bài chính. Mục 7 trình bày trường hợp khác compartment.
- Quản trị viên đã tạo bucket private `oke-report-input` và tải object nhỏ `samples/orders.csv` lên trước. Không dùng bucket chứa dữ liệu thật để thử quyền.
- Máy build có Docker; các lệnh shell dưới đây dùng cú pháp Bash. Các phép thử biến đổi manifest cần thêm `jq`.
- Một container registry và đường kéo image đã được chuẩn bị. Nếu repository private, cấu hình image pull theo cơ chế của registry trước khi chạy Job.
- Đã áp dụng policy tại mục 4, và đã chuẩn bị đường mạng từ workload tới dịch vụ.

Ghi nhận các giá trị cấu hình:

| Biến trong ví dụ | Nguồn lấy |
| --- | --- |
| `<CLUSTER_OCID>` | Chi tiết cluster OKE |
| `<LAB_COMPARTMENT_OCID>` | Compartment chứa cluster và bucket lab |
| `<OCI_REGION>` | Region chứa bucket, thí dụ `ap-singapore-1` |
| `<OBJECT_STORAGE_NAMESPACE>` | Object Storage namespace của tenancy |
| `<REGISTRY>/<REPOSITORY>:<TAG>` | Image sẽ build và đẩy lên registry |

Không cần cung cấp private key, fingerprint hay profile `~/.oci/config` cho container. Các giá trị region và tên tài nguyên là cấu hình định tuyến, không thay thế quyền IAM.

### 5.2. Tạo namespace và ServiceAccount

Nội dung `identity.yaml` trong thư mục lab của người học:

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

Áp dụng:

~~~bash
kubectl apply -f identity.yaml
kubectl get serviceaccount -n reporting
~~~

`report-untrusted` dành cho phép thử từ chối, không được đưa vào policy đọc bucket. Ví dụ không tạo RoleBinding cho ứng dụng vì ứng dụng không có nhu cầu nghiệp vụ gọi Kubernetes API.

### 5.3. Khai báo OCI SDK cho Java

Tạo project Maven có lớp `src/main/java/vn/example/oke/ObjectAccessProbe.java`. Dùng `pom.xml` sau:

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

Ví dụ cố định SDK `3.88.0` để các module dùng cùng phiên bản; đây là một bản phát hành có thật, không phải khẳng định về bản mới nhất. Khi tích hợp vào hệ thống, cập nhật đồng bộ sang phiên bản đã được đội dự án kiểm thử. [Oracle Java SDK: release 3.88.0](https://github.com/oracle/oci-java-sdk/releases/tag/v3.88.0)

OCI Java SDK 3.x yêu cầu ứng dụng chọn HTTP client implementation. Dependency Jersey 3 ở trên phục vụ việc đó; chỉ thêm module Object Storage và identity mà bỏ HTTP client có thể khiến chương trình không khởi tạo được client. [Oracle: Updates in Version 3 of the OCI SDK for Java](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdk3.htm)

### 5.4. Chương trình dùng workload identity

Chương trình có hai chế độ: `get` đọc object đã tồn tại và `put` thử tạo một object đánh dấu với tên ngẫu nhiên. Theo policy bài này, `get` phải thành công và `put` phải bị từ chối.

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

Ứng dụng đọc luồng dữ liệu và đếm byte, không đưa nội dung object vào log. Chế độ `put` dùng tên ngẫu nhiên kèm điều kiện không ghi đè; nếu policy thực tế cấp rộng hơn dự kiến, nó sẽ để lại một object đánh dấu cần được quản trị viên xóa sau khi điều tra.

Không thêm cơ chế fallback sang khóa người dùng hay instance principal cho bài thực hành này. Nếu có fallback, một lần đọc thành công chưa đủ chứng minh workload identity đã được cấu hình đúng.

### 5.5. Đóng gói image

Tạo `Dockerfile` trong project lab:

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

Giữ các dependency dưới dạng JAR riêng để không làm mất các khai báo service provider của HTTP client khi gộp JAR.

Build và đẩy image; thay đường dẫn mẫu bằng registry mà cluster có thể kéo được:

~~~bash
docker build -t <REGISTRY>/<REPOSITORY>:<TAG> .
docker push <REGISTRY>/<REPOSITORY>:<TAG>
~~~

Đăng nhập registry và quyền kéo image là bước riêng. Việc ứng dụng dùng workload identity để đọc object không tự cấu hình quyền image pull cho kubelet.

### 5.6. Gán ServiceAccount vào Job

Nội dung `workload-job.yaml`; thay toàn bộ giá trị trong dấu `<...>` trước khi chạy:

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

Với Job, đường dẫn cần chú ý là `spec.template.spec.serviceAccountName`. Đặt field ở metadata hoặc ở cấp `Job.spec` sẽ không gán danh tính cho Pod.

Nếu dùng repository private cần `imagePullSecrets`, bổ sung field tương ứng dưới `spec.template.spec` theo cấu hình đã chuẩn bị. Đừng nhầm lỗi kéo image với lỗi SDK gọi OCI.

~~~bash
kubectl apply -f workload-job.yaml
kubectl wait -n reporting --for=condition=complete job/oke-object-reader --timeout=180s
kubectl logs -n reporting job/oke-object-reader
~~~

Kết quả minh họa:

~~~text
GET_OK bytes=128 requestId=<request-id>
~~~

Số byte phụ thuộc dữ liệu đã tải lên. Log này là kết quả kỳ vọng để đối chiếu, không phải bản ghi của một lần chạy OCI trong tài liệu.

## 6. Chứng minh cả quyền được cấp lẫn giới hạn quyền

Một lần đọc thành công chỉ xác nhận trường hợp được phép. Cần chạy thêm các yêu cầu mà thiết kế phải từ chối. Giữ nguyên image, dữ liệu và cấu hình mạng giữa các lần thử để tránh nhầm nguyên nhân.

### 6.1. Đổi ServiceAccount nhưng giữ nguyên tài nguyên đích

Tạo Job mới từ manifest đã thay placeholder ở mục 5:

~~~bash
kubectl create --dry-run=client -f workload-job.yaml -o json \
  | jq '.metadata.name = "oke-object-denied-sa" | .spec.template.spec.serviceAccountName = "report-untrusted"' \
  | kubectl apply -f -

kubectl wait -n reporting --for=condition=failed job/oke-object-denied-sa --timeout=180s
kubectl logs -n reporting job/oke-object-denied-sa
~~~

Kết quả cần thấy là yêu cầu OCI bị từ chối khi dùng `report-untrusted`. Job `Failed` do không kéo được image, hết bộ nhớ, lỗi mạng hoặc hết deadline **không chứng minh** IAM đã chặn đúng principal.

Nếu Job vẫn đọc được object, kiểm tra lại ServiceAccount thực tế trong Pod, bucket có còn private không và các policy khác có cấp quyền cho principal này không. Chương trình mẫu không có fallback xác thực nên việc điều tra được thu hẹp hơn.

### 6.2. Giữ đúng ServiceAccount nhưng thử ghi

Biến đổi chế độ `MODE` sang `put` và đặt tên Job khác:

~~~bash
kubectl create --dry-run=client -f workload-job.yaml -o json \
  | jq '.metadata.name = "oke-object-denied-write" | .spec.template.spec.containers[0].env |= map(if .name == "MODE" then .value = "put" else . end)' \
  | kubectl apply -f -

kubectl wait -n reporting --for=condition=failed job/oke-object-denied-write --timeout=180s
kubectl logs -n reporting job/oke-object-denied-write
~~~

Một lỗi từ OCI phù hợp với thiếu quyền ghi là kết quả mong đợi. Nếu xuất hiện `PUT_UNEXPECTED_SUCCESS`, ghi lại tên object đánh dấu và request ID, rà soát quyền rộng hơn rồi nhờ quản trị viên xóa object đó. Không mở rộng policy chỉ để làm cho Job thử từ chối chuyển sang `Complete`.

### 6.3. Ma trận nghiệm thu cho bài thực hành

| Tình huống | Kết quả cần đạt | Điều được xác nhận |
| --- | --- | --- |
| Đúng cluster, namespace, ServiceAccount; đọc object có sẵn trong bucket được cấp | `GET_OK` | Đường xác thực, mạng và quyền đọc cùng hoạt động |
| Cùng tài nguyên nhưng dùng `report-untrusted` | OCI từ chối truy cập | Điều kiện ServiceAccount có tác dụng |
| `report-reader` thử tạo object mới trong cùng bucket | OCI từ chối ghi | Quyền đọc không bị hiểu thành quyền ghi |
| `report-reader` đọc một object có sẵn trong bucket lab thứ hai không được cấp quyền | OCI từ chối truy cập | Giới hạn tài nguyên đích có tác dụng |
| Đọc một object không tồn tại | Có thể nhận lỗi không tìm thấy | Không dùng kết quả này để kết luận đúng hay sai về quyền |

Phép thử bucket thứ hai chỉ thực hiện nếu quản trị viên đã chuẩn bị bucket private và object đối chứng trong cùng compartment. Thay `BUCKET_NAME` và `OBJECT_NAME` trong một bản Job mới; không dùng một tên bucket ngẫu nhiên rồi coi mọi lỗi 404 là bằng chứng phân quyền.

Không cần tạo thêm cluster chỉ để làm phép thử âm của bài này. Trong hệ thống có sẵn nhiều môi trường, có thể bổ sung kiểm chứng cluster OCID bằng quy trình kiểm thử tích hợp của tổ chức.

## 7. Truy cập tài nguyên ở compartment khác

Bài chính cố ý đặt cluster và bucket cùng compartment để làm rõ luồng cơ bản. Trong hệ thống thực tế, cluster có thể thuộc compartment nền tảng còn bucket thuộc compartment dữ liệu.

Trường hợp này cần cấu hình **workload mapping** theo hướng dẫn OKE cho truy cập khác compartment, bên cạnh policy dịch vụ. Mapping gắn namespace của cluster với compartment đích; điều kiện ServiceAccount trong policy vẫn dùng để phân quyền chi tiết. Không chỉ đổi OCID compartment trong câu `Allow` rồi bỏ qua bước cấu hình mapping.

Ví dụ nhóm nền tảng được giao quản lý mapping. Quản trị viên IAM đặt các statement ở vị trí có phạm vi phù hợp:

~~~text
Allow group id <PLATFORM_GROUP_OCID> to manage cluster-workload-mappings in compartment id <CLUSTER_COMPARTMENT_OCID>

Allow group id <PLATFORM_GROUP_OCID> to {CLUSTER_WORKLOAD_COMPARTMENT_BIND, CLUSTER_WORKLOAD_COMPARTMENT_UNBIND} in compartment id <DATA_COMPARTMENT_OCID>
~~~

Quyền quản lý mapping và bind/unbind compartment là quyền của người vận hành, không phải quyền ứng dụng cần để gọi `GetObject`. [Oracle: Kubernetes Engine policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/contengpolicyreference.htm)

Người có quyền thực hiện trên máy quản trị:

~~~bash
oci ce workload-mapping create \
  --cluster-id <CLUSTER_OCID> \
  --namespace reporting \
  --mapped-compartment-id <DATA_COMPARTMENT_OCID>
~~~

Ba tham số xác định cluster, namespace và compartment được ánh xạ. [Oracle CLI: workload-mapping create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ce/workload-mapping/create.html)

Sau đó, chủ sở hữu dữ liệu cấp policy đọc object trong `<DATA_COMPARTMENT_OCID>`, vẫn giữ cluster OCID, namespace, ServiceAccount và bucket đích như mục 4. Vì mapping áp dụng ở mức namespace, cần đánh giá tác động với các workload khác trong namespace trước khi tạo hoặc thay đổi mapping.

Nếu đã có mapping, kiểm tra cấu hình hiện hữu và quyền quản trị trước khi điều chỉnh. Quản lý mapping trong cùng quy trình thay đổi hạ tầng với policy giúp tránh tình trạng policy đã chuyển sang compartment mới nhưng binding vẫn ở cấu hình cũ. [Oracle: quy trình truy cập tài nguyên khác compartment](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)

## 8. Đường mạng: quyền IAM không tạo ra kết nối

Với Pod chạy trong private subnet, Object Storage vẫn có thể được truy cập qua service gateway của VCN. Route và security rules phải cho phép đường đi tới Oracle Services Network trong region. Service gateway chỉ phục vụ các dịch vụ được hỗ trợ; truy cập Internet để tải dependency hoặc truy cập dịch vụ ngoài phạm vi đó cần đường mạng khác. [Oracle: Access to Oracle Services — Service Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm)

Khi kiểm tra đường mạng, tách hai chặng:

| Chặng | Nội dung cần xác minh |
| --- | --- |
| Pod tới luồng xác thực OKE | Môi trường cluster hỗ trợ identity; token được mount; kết nối tới endpoint xác thực theo cấu hình OKE và SDK không bị chặn |
| Pod tới Object Storage | DNS phân giải được endpoint; route đúng; egress HTTPS được phép; TLS tin cậy chứng thư |

Trong CNI có mạng Pod riêng, xem đúng subnet, route table và NSG tham gia đường đi của Pod; không mặc định mọi gói tin đều theo cấu hình subnet của node. Đồng thời kiểm tra NetworkPolicy hoặc proxy/sidecar nếu ứng dụng sử dụng các thành phần đó.

Một policy IAM hoàn toàn đúng vẫn không sửa được DNS timeout. Một route hoàn toàn đúng cũng không cho phép `report-untrusted` đọc bucket. Vì vậy không thêm `manage all-resources` để xử lý lỗi socket hay TLS.

Image pull còn là một luồng khác: nó xảy ra trước khi chương trình Java chạy. Nếu Pod ở trạng thái `ImagePullBackOff`, hãy sửa registry, quyền kéo image và đường mạng của quá trình kéo image trước khi điều tra workload identity trong chương trình.

## 9. Mở rộng cùng danh tính sang dịch vụ OCI khác

Workload identity giải quyết phần xác thực. Mỗi dịch vụ vẫn có resource type, permission và endpoint riêng. Khi thêm một nhu cầu, liệt kê API ứng dụng thực sự gọi rồi đối chiếu policy reference của dịch vụ đó.

### 9.1. Đọc một secret để kết nối cơ sở dữ liệu

Nếu ứng dụng cần lấy mật khẩu của cơ sở dữ liệu từ OCI Secret Management, có thể dùng cùng provider để tạo client của dịch vụ Secrets. Policy minh họa dưới đây chỉ nhắm một secret trong compartment cùng phạm vi đã cấu hình:

~~~text
Allow any-user to read secret-bundles in compartment id <SECRET_COMPARTMENT_OCID> where all {
  request.principal.type = 'workload',
  request.principal.cluster_id = '<CLUSTER_OCID>',
  request.principal.namespace = 'reporting',
  request.principal.service_account = 'report-reader',
  target.secret.id = '<SECRET_OCID>'
}
~~~

`GetSecretBundle` cần quyền đọc secret bundle. `read secrets` dùng cho metadata của secret và không thay cho quyền lấy nội dung bundle. [Oracle: Vault, Key Management, and Secret Management policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/keypolicyreference.htm)

Nếu secret ở compartment khác cluster, xử lý mapping trước như mục 7. Không đưa secret giải mã vào log, image hoặc Git. Việc lấy secret thành công cũng không tạo quyền trong cơ sở dữ liệu: ứng dụng vẫn phải kết nối tới DB bằng cơ chế xác thực phù hợp và một tài khoản có quyền SQL cần thiết.

Có hai luồng khác nhau cần thiết kế riêng: gọi API OCI để quản lý tài nguyên cơ sở dữ liệu, và kết nối vào database để chạy truy vấn. Workload identity không khiến mọi JDBC connection tự động được xác thực hay tự có quyền truy cập bảng.

### 9.2. Thay đổi quyền theo thành phần ứng dụng

Một hệ thống báo cáo có thể tách:

| Thành phần | ServiceAccount đề xuất | Phạm vi nghiệp vụ |
| --- | --- | --- |
| Bộ đọc đầu vào | `report-reader` | Đọc dữ liệu nguồn |
| Bộ xuất kết quả | `report-writer` | Ghi vào nơi nhận kết quả đã xác định |
| Thành phần lấy cấu hình DB | `report-db-client` | Đọc đúng secret cần thiết |

Đây là thiết kế minh họa. Không sao chép nguyên policy đọc bucket cho thành phần ghi; phải ánh xạ lại các API ghi, quyền tạo mới/ghi đè và tài nguyên đích.

## 10. Giám sát và đối chiếu yêu cầu

Log ứng dụng nên đủ để trả lời: thao tác nào thất bại, lúc nào, với mã HTTP/service code nào và request ID nào. Có thể bổ sung tên môi trường, namespace và ServiceAccount từ cấu hình triển khai; các nhãn do ứng dụng tự ghi chỉ hỗ trợ tra cứu, không thay cho danh tính đã được hệ thống xác thực.

Với bài thực hành, giữ lại:

- Tên Job/Pod và thời gian thực hiện.
- Chế độ `get` hoặc `put`, cùng tài nguyên lab liên quan.
- `requestId` trả về từ OCI nếu có.
- Kết quả đối chiếu với ma trận quyền.

**OCI Audit không ghi các sự kiện Object Storage ở mức object như `GetObject`**; tài liệu Audit nêu phạm vi hỗ trợ Object Storage ở mức bucket. Dùng Audit để xem những thay đổi quản trị được hỗ trợ, không kỳ vọng tìm mọi lần đọc object ở đó. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm)

Muốn theo dõi thao tác đọc/ghi object, bật **Read Access Events** và **Write Access Events** của bucket qua OCI Logging theo nhu cầu. Log đọc bao gồm các nhóm thao tác GET/LIST/HEAD; log ghi bao gồm PUT/POST/DELETE. Việc chuyển log được thực hiện theo cơ chế best effort, nên không dùng sự vắng mặt tức thời của một bản ghi làm bằng chứng duy nhất rằng yêu cầu chưa xảy ra. [Oracle: Logging details for Object Storage](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/details_for_object_storage.htm)

Bảo vệ quyền đọc log và chọn retention theo yêu cầu vận hành. Tránh bật HTTP wire logging chứa Authorization header hoặc in token để tìm danh tính. Với ứng dụng nhiều replica, theo dõi tỷ lệ lỗi xác thực và độ trễ gọi OCI để nhận biết vấn đề sau khi rollout, mở rộng hoặc thay đổi mạng.

## 11. Chẩn đoán theo triệu chứng

Bắt đầu bằng trạng thái Pod và cấu hình thực tế đã triển khai:

~~~bash
kubectl get pods -n reporting -l app=oke-object-access-probe -o wide
kubectl describe job -n reporting oke-object-reader
kubectl describe pod -n reporting -l job-name=oke-object-reader
kubectl get pods -n reporting -l job-name=oke-object-reader \
  -o custom-columns=NAME:.metadata.name,SA:.spec.serviceAccountName,PHASE:.status.phase
kubectl logs -n reporting job/oke-object-reader
~~~

| Triệu chứng | Kiểm tra trước | Cách xử lý có mục tiêu |
| --- | --- | --- |
| `ImagePullBackOff` | Registry, image tag/digest, pull secret và kết nối kéo image | Sửa đường kéo image; chưa kết luận về identity trong ứng dụng |
| Provider không khởi tạo được | Loại cluster, dependency identity, token mount và môi trường SDK | Chạy trên enhanced cluster; dùng provider và dependency tương thích |
| Không tìm thấy HTTP client implementation | Dependency Jersey/Jersey 3 có trong runtime classpath không | Bổ sung implementation phù hợp và giữ khai báo service provider khi đóng gói |
| Lỗi xác thực hoặc 401 | Token, provider đang dùng, đường tới luồng xác thực và thời gian hệ thống | Xác minh môi trường xác thực; không chữa bằng quyền tài nguyên rộng hơn |
| `NotAuthorizedOrNotFound`, 403 hoặc 404 từ dịch vụ | Bộ ba identity, bucket/object thật, region, policy và mapping | Đối chiếu từng điều kiện và dùng object đã được quản trị viên xác nhận tồn tại |
| DNS timeout, connect timeout | DNS, route, NSG/security list, NetworkPolicy, proxy | Kiểm tra chặng mạng tương ứng |
| Lỗi chứng thư TLS | Trust store, proxy và chứng thư endpoint | Sửa trust chain; giữ xác minh TLS |
| Đọc được nhưng ghi bị từ chối | Verb/resource type và API ghi | Nếu workload chỉ đọc thì đây là kết quả đúng; nếu cần ghi, thiết kế quyền riêng |
| Job bị `DeadlineExceeded` | Retry, độ trễ mạng và thời gian build/startup | Phân biệt hết ngân sách thời gian với IAM deny |
| Phép thử sai ServiceAccount vẫn thành công | ServiceAccount trong Pod và toàn bộ policy áp dụng | Tìm quyền dư hoặc cấu hình triển khai sai trước khi nghiệm thu |

Không dùng `kubectl auth can-i` để kết luận quyền Object Storage: lệnh đó hỏi cơ chế phân quyền Kubernetes. Nó hữu ích khi điều tra quyền tạo Job, đọc log hoặc tác động vào tài nguyên Kubernetes.

Với token mount, kiểm tra sự hiện diện và khả năng đọc file tại đường dẫn provider sử dụng, không sao chép nội dung token ra terminal. Khi cần thử lại Job sau khi sửa cấu hình, tạo tên Job mới hoặc xóa đúng Job lab cũ rồi tạo lại; Pod template của Job có các field không thể cập nhật tùy ý.

## 12. Quản trị vòng đời quyền và khả năng sẵn sàng

### 12.1. Bảo vệ việc sử dụng ServiceAccount

Theo mô hình của bài, Pod mang `report-reader` có thể dùng quyền đọc đã cấp. Vì vậy, quyền tạo Pod/Job/Deployment trong namespace hoặc quyền sửa pod template là một phần của bề mặt cấp quyền tới dữ liệu OCI.

Giới hạn người và pipeline được triển khai vào namespace `reporting`. Nếu cần kiểm soát trường `serviceAccountName`, dùng admission policy phù hợp với nền tảng; một RoleBinding thông thường không diễn đạt đầy đủ việc chỉ cho phép chọn một ServiceAccount trong mọi pod template. Cũng xem xét quyền exec vào Pod và quyền yêu cầu token ServiceAccount.

Một người chỉ được deploy ứng dụng không nên mặc nhiên có quyền sửa IAM policy hoặc workload mapping. Tách trách nhiệm này giúp việc review ranh giới dữ liệu rõ ràng hơn.

### 12.2. Triển khai và thay đổi có thể lặp lại

Trong quy trình hạ tầng tự động, quản lý cùng nhau các giá trị liên quan: cluster OCID, namespace, ServiceAccount, compartment đích, bucket và policy. Giữ sự tương ứng giữa manifest ứng dụng và IAM dưới kiểm soát phiên bản, nhưng không đưa thông tin xác thực phiên vào kho mã nguồn.

Khi chuyển sang cluster phục hồi sau sự cố, cluster OCID mới phải được tính trong thiết kế quyền. Namespace và ServiceAccount trùng tên chưa đủ làm policy cũ áp dụng cho cluster mới. Chuẩn bị policy/mapping và phép thử đọc trước khi chuyển tải; giới hạn rõ thời gian nếu hai cluster cùng được cấp quyền.

Với dịch vụ Java chạy dài hạn, kiểm chứng khả năng tiếp tục gọi OCI sau các chu kỳ xoay token trong kiểm thử tích hợp. Job ngắn của bài này chỉ minh họa truy cập và giới hạn quyền tại thời điểm chạy.

### 12.3. Thu hồi khi ngừng dùng hoặc có sự cố

Quy trình thu hồi cần gắn với nguyên nhân:

1. Dừng hoặc cô lập workload đang có vấn đề để ngăn yêu cầu mới từ tiến trình đó.
2. Thu hẹp hoặc xóa statement IAM cấp quyền cho danh tính bị ảnh hưởng.
3. Kiểm tra workload mapping và các ServiceAccount dùng chung trước khi thay đổi hoặc xóa.
4. Xác minh lại từ một tiến trình mới, đồng thời tính tới thời gian lan truyền policy và thông tin xác thực đã được cache.
5. Đối chiếu log và xử lý dữ liệu đã bị truy cập hoặc object đánh dấu đã được tạo ngoài dự kiến.

Không lấy việc xóa một Pod làm bằng chứng duy nhất rằng toàn bộ quyền đã được thu hồi: controller có thể tạo Pod thay thế với cùng ServiceAccount, và các replica khác vẫn tồn tại.

## 13. Chi phí và dọn tài nguyên lab

Workload identity không làm các tài nguyên sử dụng trở thành miễn phí. Trong bài thực hành, các yếu tố cần theo dõi gồm cluster enhanced, worker node hoặc loại node sử dụng, dung lượng và request Object Storage, log được lưu, registry và đường truyền dữ liệu.

Chọn object nhỏ, giới hạn số Job chạy lại và giữ `backoffLimit: 0` khi đang xác minh lỗi quyền để tránh tạo thêm yêu cầu lặp khó quan sát. Trong production, thiết kế retry có giới hạn theo loại lỗi; lặp lại liên tục lỗi IAM không tự làm phát sinh quyền.

Sau khi lưu bằng chứng thực hành, xóa đúng ba Job và hai ServiceAccount đã tạo:

~~~bash
kubectl delete job -n reporting \
  oke-object-reader oke-object-denied-sa oke-object-denied-write \
  --ignore-not-found

kubectl delete serviceaccount -n reporting \
  report-reader report-untrusted \
  --ignore-not-found
~~~

Nếu đã tạo Job bổ sung để thử bucket thứ hai, xóa đúng Job đó. Không xóa cả namespace khi namespace còn chứa workload khác.

Người quản trị gỡ statement IAM riêng cho lab, xóa mapping riêng của lab nếu có và đã kiểm tra tác động, xử lý object đánh dấu nếu phép thử ghi thành công ngoài dự kiến, rồi dọn image, bucket hoặc hạ tầng chỉ được tạo cho bài học. Với cluster dùng chung, dọn tài nguyên ứng dụng theo phạm vi đã cấp.

Một triển khai đạt mục tiêu của bài có đủ bằng chứng đọc được dữ liệu cần thiết, từ chối được danh tính/thao tác ngoài phạm vi, tra được lỗi qua request ID và thu hồi được quyền theo quy trình quản trị.
