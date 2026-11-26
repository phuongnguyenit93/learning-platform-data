# Kiểm thử quyền thiếu, token hết hạn và chứng chỉ không hợp lệ

## 1. Mục tiêu và bối cảnh

Trong chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**, bài này xây dựng kiểm thử khi ứng dụng Spring không thể truy cập Kubernetes API vì thiếu quyền, token hết hạn hoặc lỗi chứng chỉ. Mục tiêu là chứng minh ứng dụng nhận diện đúng nguyên nhân, giữ nguyên bảo vệ TLS và phục hồi có kiểm soát sau khi nguyên nhân được khắc phục.

Xét ứng dụng `catalog-service` đọc cấu hình từ ConfigMap, có thể đọc Secret, tìm Pod của dịch vụ qua DiscoveryClient và chọn instance bằng Spring Cloud LoadBalancer. Configuration Watcher có thể là một workload riêng theo dõi thay đổi cấu hình. Những thành phần này không nhất thiết dùng cùng ServiceAccount, cùng client hoặc cùng đường kết nối.

Sau bài học, bạn có thể:

- Tạo fixture RBAC tối thiểu để sinh lỗi `403` có chủ đích.
- Kiểm thử `401` bằng token thực sự hết hạn mà không nhầm với JWT sai chữ ký.
- Tạo lỗi CA, SAN và thời hạn chứng chỉ trong môi trường kiểm thử.
- Kiểm tra khởi động, retry, readiness và phục hồi của ứng dụng dùng Spring Cloud Kubernetes.
- Phân biệt bằng chứng từ HTTP client độc lập với bằng chứng từ chính ứng dụng Spring.

Các ví dụ dùng JUnit 5 và Java 17 trở lên. Chúng là mã tham khảo để đưa vào dự án kiểm thử của người học; bài không giả định một phiên bản Spring Boot, Spring Cloud hay Kubernetes client cụ thể. Hãy khóa bộ phiên bản tương thích của dự án trước khi chạy.

## 2. Ba lớp lỗi cần phân biệt

Một yêu cầu HTTPS đến Kubernetes API đi qua ba bước chính:

~~~mermaid
flowchart LR
    A["Client của ứng dụng Spring"] --> B["TLS: CA, thời hạn, SAN"]
    B -->|Hợp lệ| C["Authentication: xác minh token"]
    C -->|Nhận diện được ServiceAccount| D["Authorization: kiểm tra quyền"]
    D -->|Cho phép| E["Đọc ConfigMap, Secret hoặc discovery"]
    B -->|Không hợp lệ| F["Lỗi TLS; không có HTTP response"]
    C -->|Token bị từ chối| G["HTTP 401"]
    D -->|Thiếu quyền| H["HTTP 403"]
~~~

Đường API server phải được kiểm tra đúng CA và đúng tên máy chủ. Không thể dùng một lỗi HTTP để mô tả việc client từ chối chứng chỉ server ngay trong bắt tay TLS. Đây là các giai đoạn khác nhau của [kiểm soát truy cập Kubernetes API](https://kubernetes.io/docs/concepts/security/controlling-access/).

| Tình huống | Lớp lỗi chủ yếu | Bằng chứng cần thu |
| --- | --- | --- |
| Token còn hạn, ServiceAccount không được đọc ConfigMap | Authorization | HTTP `403`; resource, namespace và verb bị từ chối |
| Token đã hết hạn được gửi rõ ràng trong Bearer header | Authentication | HTTP `401` từ API server |
| Client không tin CA ký chứng chỉ server | TLS | Lỗi handshake/certificate validation; không có response HTTP thành công |
| Chứng chỉ server không chứa hostname/IP đang truy cập trong SAN phù hợp | TLS | Lỗi xác minh danh tính máy chủ |
| Chứng chỉ server đã hết hạn | TLS | Lỗi kiểm tra thời hạn chứng chỉ |
| DNS sai, kết nối bị chặn hoặc server không lắng nghe | Kết nối | Lỗi DNS, connection refused hoặc timeout; chưa đủ kết luận về TLS |

Không gửi token là một tình huống khác với gửi token hết hạn. Nếu anonymous authentication được bật, yêu cầu không có credentials có thể trở thành `system:anonymous` rồi nhận `403` hoặc được cho phép ở một số endpoint. Trong ca kiểm thử token hết hạn, phải gửi token một cách tường minh và tránh credentials khác xác thực thay thế. Xem [quy tắc authentication của Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/authentication/).

Bài chủ yếu xét **chứng chỉ server** mà client phải xác minh. Nếu ứng dụng dùng mTLS, chứng chỉ **client** không hợp lệ cần ca kiểm thử riêng; thời điểm từ chối còn phụ thuộc cấu hình TLS và authentication phía server. Không gộp hai hướng xác minh thành một kỳ vọng duy nhất.

## 3. Xác định hợp đồng hành vi trước khi tạo lỗi

Một negative test chỉ có ý nghĩa khi biết ứng dụng phải làm gì. Đặt hợp đồng cho từng tính năng và phân biệt cấu hình bắt buộc với cấu hình tùy chọn.

| Thành phần | Khi gặp lỗi xác thực, phân quyền hoặc TLS | Điều kiện phục hồi |
| --- | --- | --- |
| ConfigMap bắt buộc khi khởi động | Khởi động thất bại trong thời hạn xác định; không phục vụ request bằng cấu hình mặc định nguy hiểm | Khởi động lại hoặc retry hữu hạn sau khi credentials/quyền/CA được sửa |
| Secret bắt buộc | Không công bố sẵn sàng khi thiếu dữ liệu cần thiết; log không lộ giá trị Secret | Nạp được Secret hợp lệ rồi mới đáp ứng hợp đồng sẵn sàng |
| DiscoveryClient | Phản ánh được lỗi hoặc trạng thái dữ liệu quá cũ; không coi danh sách rỗng là bằng chứng duy nhất | Đọc được danh sách mới và chọn đúng instance sau khi khôi phục |
| Spring Cloud LoadBalancer dựa trên discovery | Không gửi request đến instance bị loại khỏi tập hợp hợp lệ theo chính sách cache đã định | Chọn được instance mới sau khi discovery cập nhật |
| Configuration Watcher | Báo lỗi truy cập API hoặc mất watch; không báo đã đồng bộ khi chưa đọc được thay đổi | Thiết lập lại kết nối và nhận được thay đổi mới |
| API nghiệp vụ có cấu hình dự phòng được chấp nhận | Tiếp tục trong chế độ suy giảm đã công bố, có giới hạn tuổi dữ liệu và khả năng quan sát | Trở về trạng thái bình thường sau khi đồng bộ thành công |

Đây là **hợp đồng kiểm thử đề xuất**, không phải cam kết rằng mọi starter tự cung cấp đầy đủ các hành vi trên. Chẳng hạn, fail-fast khi tải cấu hình lúc khởi động không tự trở thành cơ chế readiness cho một watch bị lỗi khi ứng dụng đã chạy.

Ví dụ, với `catalog-service`, nhóm phát triển có thể quyết định:

1. Không khởi động thành công nếu không đọc được cấu hình bắt buộc.
2. Trong khi đang chạy, cho phép dùng bản cấu hình hợp lệ gần nhất tối đa 120 giây.
3. Quá thời hạn đó, readiness chuyển sang không sẵn sàng; liveness vẫn phản ánh khả năng hoạt động của tiến trình.
4. Sau khi đồng bộ lại, readiness chỉ trở lại sẵn sàng khi đọc được phiên bản cấu hình mong đợi.

Nếu chọn chính sách này, ứng dụng phải có phần theo dõi thời điểm đồng bộ và health contributor tương ứng. Kiểm thử không được giả định Kubernetes tự biết cấu hình trong bộ nhớ đã quá cũ.

## 4. Chia kiểm thử thành ba tầng

### 4.1. Kiểm thử logic trong tiến trình

Dùng fake hoặc mock tại ranh giới client để kiểm tra:

- Phân loại `401`, `403` và lỗi TLS thành nguyên nhân có ý nghĩa.
- Retry có giới hạn, không lặp vô hạn với cùng token đã bị từ chối.
- Log che Bearer token, Secret và dữ liệu nhạy cảm.
- Bản cấu hình đang dùng không bị thay bằng dữ liệu rỗng sau một lần tải thất bại.
- Readiness thay đổi đúng chính sách ứng dụng.

Một mock trả `401` chỉ chứng minh logic xử lý `401`. Nó không chứng minh API server đã kiểm tra chữ ký hoặc thời hạn JWT.

### 4.2. Kiểm thử giao thức với Kubernetes API thật

Dùng cluster dành cho kiểm thử, bật RBAC, ServiceAccount riêng và namespace riêng cho từng lần chạy. Tầng này xác minh rằng fixture thật sự tạo ra `200`, `401` hoặc `403` như dự kiến.

Danh tính bootstrap của CI chỉ được dùng để tạo tài nguyên và cấp fixture. Client đang kiểm thử phải dùng Bearer token của ServiceAccount mục tiêu, không được vô tình đọc kubeconfig quản trị.

### 4.3. Kiểm thử tích hợp bằng ứng dụng Spring

Chạy đúng starter và backend client của ứng dụng: Fabric8, Kubernetes Java Client hoặc đường discovery qua HTTP nếu dự án chọn kiến trúc đó. Các kiểu DiscoveryClient có đường truy cập khác nhau; xem [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Ghi rõ trong báo cáo kiểm thử:

| Thuộc tính | Ví dụ thông tin cần ghi |
| --- | --- |
| Bộ phiên bản | Spring Boot, Spring Cloud release train, Spring Cloud Kubernetes, Kubernetes client |
| Tính năng đang bật | API ConfigMap, API Secret, discovery, watcher, cache |
| Đường truy cập | Ứng dụng → API server; hoặc ứng dụng → DiscoveryServer → API server |
| Danh tính | ServiceAccount và namespace của từng workload |
| Cách nạp cấu hình | API trực tiếp, file mount hoặc cơ chế khác |
| Cách truy cập dịch vụ | Kubernetes DNS/Service hoặc DiscoveryClient + LoadBalancer |
| Ngân sách thời gian | Timeout mỗi request, tổng retry, thời gian phục hồi tối đa |

Nếu ứng dụng chỉ gọi dịch vụ bằng DNS và đọc cấu hình từ file mount, ứng dụng có thể không cần gọi Kubernetes API. Khi đó, kiểm thử đúng đường phụ thuộc thực tế; không bật thêm discovery hay cấp quyền Secret chỉ để có đủ ca kiểm thử.

## 5. Tạo fixture RBAC có thể lặp lại

### 5.1. Điều kiện chạy

Các lệnh dưới đây là **Bash** dành cho runner Linux hoặc môi trường Bash tương đương. Chỉ dùng cluster kiểm thử đã được chọn tường minh.

- `TEST_CONTEXT` trỏ đến cluster kiểm thử.
- Danh tính bootstrap được tạo namespace, ConfigMap, ServiceAccount, Role, RoleBinding và gọi TokenRequest.
- Cluster dùng RBAC và không có quyền cấp rộng cho tất cả ServiceAccount của namespace kiểm thử.
- Runner kết nối được trực tiếp tới API server qua HTTPS.

Tạo thư mục fixture riêng và giới hạn quyền truy cập vì các tệp JWT là credentials:

~~~bash
set -euo pipefail
: "$TEST_CONTEXT"

k() {
  kubectl --context "$TEST_CONTEXT" "$@"
}

NS="sck-auth-$(date +%s)-$RANDOM"
umask 077
FIXTURES="$(mktemp -d)"

k create namespace "$NS"

k -n "$NS" apply -f - <<'YAML'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: sck-reader
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: sck-no-access
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-service
data:
  lesson.marker: baseline-v1
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: config-reader
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: config-reader
subjects:
  - kind: ServiceAccount
    name: sck-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: config-reader
YAML

k -n "$NS" create token sck-reader --duration=20m \
  > "$FIXTURES/reader.jwt"

k -n "$NS" create token sck-no-access --duration=20m \
  > "$FIXTURES/no-access.jwt"

export TEST_NAMESPACE="$NS"
export READER_TOKEN_FILE="$FIXTURES/reader.jwt"
export NO_ACCESS_TOKEN_FILE="$FIXTURES/no-access.jwt"
~~~

Fixture cố ý không cấp quyền đọc Secret. Chỉ thêm Secret thử nghiệm không chứa dữ liệu thật nếu ca kiểm thử yêu cầu.

RBAC cộng dồn quyền từ các binding; không có rule “deny” để phủ định quyền được cấp ở nơi khác. Vì vậy, ServiceAccount không có RoleBinding riêng vẫn có thể được hưởng quyền rộng qua binding khác. Negative test phải xác nhận trạng thái thực tế trước khi kết luận fixture đúng. Xem [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

### 5.2. Chọn đúng endpoint và CA

Đặt `KUBE_API_URL` bằng endpoint HTTPS mà runner thực sự truy cập được. Đặt `KUBE_CA_FILE` bằng tệp PEM chứa CA/bundle phù hợp cho endpoint đó, lấy từ cấu hình tin cậy của cluster kiểm thử.

Trong cluster thông thường, ConfigMap `kube-root-ca.crt` trong namespace có CA phục vụ việc xác minh API server. Tuy nhiên, endpoint đi qua proxy TLS bên ngoài có thể dùng chuỗi chứng chỉ khác. Không chọn CA chỉ vì tên tệp trông hợp lý. Sau khi tạo namespace, có thể phải chờ bộ điều khiển xuất bản ConfigMap CA.

Hợp đồng biến môi trường của bộ kiểm thử:

| Biến | Ý nghĩa |
| --- | --- |
| `KUBE_API_URL` | Ví dụ `https://api.test.example:6443`, không kèm path |
| `KUBE_CA_FILE` | Tệp PEM CA tin cậy của endpoint |
| `TEST_NAMESPACE` | Namespace vừa tạo |
| `READER_TOKEN_FILE` | Token còn hạn của `sck-reader` |
| `NO_ACCESS_TOKEN_FILE` | Token còn hạn của `sck-no-access` |
| `EXPIRED_TOKEN_FILE` | Token đã được xác nhận hết hạn; chỉ cần cho ca hết hạn |

Trước mỗi ca âm, phải có một ca dương: cùng endpoint và CA, token reader còn hạn đọc được ConfigMap `catalog-service`, nhận `200` và giá trị `lesson.marker=baseline-v1`. Nếu ca dương thất bại, báo lỗi fixture; không tính ca âm là thành công.

### 5.3. Kiểm tra RBAC bằng impersonation chỉ là bước hỗ trợ

~~~bash
k auth can-i get configmaps \
  --namespace "$NS" \
  --as "system:serviceaccount:$NS:sck-reader"

k auth can-i get configmaps \
  --namespace "$NS" \
  --as "system:serviceaccount:$NS:sck-no-access"
~~~

Danh tính bootstrap phải có quyền impersonate để chạy hai lệnh này. Kết quả giúp kiểm tra mô hình cấp quyền, nhưng không kiểm tra chữ ký, audience, thời hạn token hay TLS mà client ứng dụng sử dụng. Ca chính vẫn phải gửi token thật bằng client không mang credentials quản trị.

## 6. Client kiểm thử độc lập để xác minh 200 và 403

Ví dụ sau dùng JDK `HttpClient` và JUnit 5. Nó chỉ cài trust material, không cài client certificate, không dùng kubeconfig và không đọc token từ cơ chế tự động khác. Vì vậy, Bearer token của ca kiểm thử là credentials duy nhất được gửi.

~~~java
import org.junit.jupiter.api.Test;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.time.Duration;
import java.util.Collection;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KubernetesAccessIT {

    static String env(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing test input: " + name);
        }
        return value;
    }

    static HttpClient client(Path caFile) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        Collection<? extends Certificate> certificates;
        try (InputStream in = Files.newInputStream(caFile)) {
            certificates = factory.generateCertificates(in);
        }
        if (certificates.isEmpty()) {
            throw new IllegalArgumentException("CA bundle is empty");
        }

        KeyStore trustStore = KeyStore.getInstance(KeyStore.getDefaultType());
        trustStore.load(null, null);
        int index = 0;
        for (Certificate certificate : certificates) {
            trustStore.setCertificateEntry("ca-" + index++, certificate);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustStore);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(null, tmf.getTrustManagers(), null);

        return HttpClient.newBuilder()
                .sslContext(tls)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    static URI configMapUri() {
        String base = env("KUBE_API_URL").replaceAll("/+$", "");
        URI endpoint = URI.create(base);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException("KUBE_API_URL must use HTTPS");
        }
        String namespace = env("TEST_NAMESPACE");
        if (!namespace.matches("[a-z0-9]([-a-z0-9]*[a-z0-9])?")) {
            throw new IllegalArgumentException("Invalid namespace fixture");
        }
        return URI.create(base + "/api/v1/namespaces/" + namespace
                + "/configmaps/catalog-service");
    }

    static HttpResponse<Void> getWithToken(
            HttpClient client, String token) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(configMapUri())
                .header("Authorization", "Bearer " + token)
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        return client.send(request, HttpResponse.BodyHandlers.discarding());
    }

    static String token(String variable) throws Exception {
        String value = Files.readString(Path.of(env(variable))).strip();
        if (value.isBlank()) {
            throw new IllegalArgumentException("Empty token fixture: " + variable);
        }
        return value;
    }

    @Test
    void validReaderCanReadConfigMap() throws Exception {
        HttpResponse<Void> response = getWithToken(
                client(Path.of(env("KUBE_CA_FILE"))),
                token("READER_TOKEN_FILE"));
        assertEquals(200, response.statusCode());
    }

    @Test
    void validIdentityWithoutPermissionGets403() throws Exception {
        HttpClient client = client(Path.of(env("KUBE_CA_FILE")));

        // Ca dương trong cùng phép thử để tránh nhận nhầm lỗi fixture.
        assertEquals(200, getWithToken(
                client, token("READER_TOKEN_FILE")).statusCode());

        HttpResponse<Void> response = getWithToken(
                client, token("NO_ACCESS_TOKEN_FILE"));
        assertEquals(403, response.statusCode());
        assertTrue(response.headers()
                .firstValue("content-type")
                .orElse("")
                .contains("json"));
    }
}
~~~

Mã dùng `BodyHandlers.discarding()` để tránh vô tình đưa dữ liệu cấu hình vào báo cáo lỗi. Ca kiểm tra marker `baseline-v1` nên phân tích body bằng JSON parser ở một phép thử dương riêng, không in toàn bộ body.

`SSLContext` tùy chỉnh chỉ giới hạn CA tin cậy, không được thay bằng trust manager chấp nhận mọi chứng chỉ. Hostname verification vẫn phải hoạt động. Các tham số timeout và TLS của builder được mô tả trong [JDK HttpClient.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html).

Đây là probe giao thức, chưa kiểm tra việc starter Spring chọn token, nạp cấu hình hoặc làm mới credentials. Phải có thêm kiểm thử bằng ứng dụng thật ở phần 10.

## 7. Kiểm thử thiếu từng quyền thay vì chỉ bỏ toàn bộ Role

Sau fixture “không có quyền đọc”, xây dựng các biến thể Role riêng cho từng ca:

| Biến thể | Phép gọi chủ động | Kỳ vọng |
| --- | --- | --- |
| Chỉ cấp `get` ConfigMap | GET ConfigMap theo tên | Thành công |
| Chỉ cấp `get` ConfigMap | GET danh sách ConfigMap | `403` |
| Cấp `get,list` nhưng thiếu `watch` | Mở yêu cầu watch mới | `403` khi mở watch |
| Đủ quyền trong namespace A | Đọc cùng loại resource ở namespace B | `403` nếu không có quyền khác |
| Đọc được ConfigMap, không được đọc Secret | GET Secret thử nghiệm theo tên | `403` |
| Đọc được Service nhưng không đọc được EndpointSlice | Discovery đã cấu hình dùng EndpointSlice | Phát hiện lỗi đọc nguồn endpoint và hành vi suy giảm |

HTTP `GET` vào một đối tượng và HTTP `GET` vào collection tương ứng với quyền RBAC khác nhau: `get` và `list`. Không suy ra “đã đọc được một ConfigMap” nghĩa là khởi động ứng dụng chắc chắn thành công.

Tùy phiên bản và chế độ đọc, Spring Cloud Kubernetes có thể liệt kê rồi lọc hoặc truy vấn theo tên. Discovery cũng có thể dùng Endpoints hay EndpointSlice. Kiểm thử cần khóa lựa chọn của dự án, quan sát request thực tế và tạo Role phù hợp; không dùng một manifest quyền như chân lý cho mọi backend.

Ca thu hồi `watch` phải đóng watch cũ và mở kết nối mới. Không giả định một kết nối watch đã được chấp nhận sẽ bị ngắt ngay khi sửa RoleBinding. Dùng namespace/Role riêng cho từng ca để tránh các bài kiểm thử song song thay đổi quyền của nhau.

## 8. Kiểm thử token thực sự hết hạn

### 8.1. Tạo fixture có nguồn gốc rõ ràng

Token ServiceAccount cấp qua TokenRequest có thời hạn. Với `kubectl create token`, `--duration` là thời hạn yêu cầu; API server có thể cấp thời hạn khác. Phải đọc `exp` thực tế thay vì giả định token hết hạn sau đúng số phút trong lệnh. Xem [kubectl create token](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_token/).

Một quy trình kiểm thử thời hạn đáng tin cậy:

1. Tạo token cho `sck-reader` bằng TokenRequest trên cluster kiểm thử.
2. Ngay khi nhận token, gửi request và xác nhận `200`.
3. Lưu token vào tệp fixture riêng, ghi nhận thời điểm phát hành, `exp`, cluster và ServiceAccount của ca thử. Không lưu nguyên JWT vào log.
4. Giữ nguyên API server, ServiceAccount và các tài nguyên liên quan trong suốt ca.
5. Chờ qua `exp` thực tế và biên thời gian đã chọn; sau đó dùng **đúng token cũ** để gọi lại.
6. Xác nhận token cũ nhận `401` trong khi một token mới của cùng ServiceAccount vẫn nhận `200`.

Ví dụ yêu cầu token có thời hạn ngắn cho lượt kiểm thử chuyên biệt:

~~~bash
k -n "$NS" create token sck-reader --duration=10m \
  > "$FIXTURES/expiring.jwt"

export EXPIRED_TOKEN_FILE="$FIXTURES/expiring.jwt"
~~~

Đặt tên biến `EXPIRED_TOKEN_FILE` không khiến tệp lập tức hết hạn. Sau lệnh trên, fixture mới chỉ là **token sẽ hết hạn**. Bộ điều phối phải thực hiện baseline và đợi theo claim `exp` trước khi chạy kiểm thử bên dưới.

Nếu thời gian chờ vượt ngân sách pull request, tách ca hết hạn thật sang một job kiểm thử dài. Giữ ca mock `401` trong pipeline nhanh. Không chuyển toàn bộ ca mock thành bằng chứng rằng lifecycle token đã được kiểm tra trên cluster thật.

### 8.2. Đọc exp để kiểm tra tiền điều kiện

Ví dụ này dùng thêm Jackson Databind trong test classpath để phân tích JSON; hai lớp kiểm thử đặt cùng package để tái sử dụng `KubernetesAccessIT`.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.http.HttpClient;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Base64;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ExpiredServiceAccountTokenIT {

    static long expiration(String jwt) throws Exception {
        String[] parts = jwt.split("\\.");
        if (parts.length != 3) {
            throw new IllegalArgumentException("Expected a JWT fixture");
        }

        byte[] payload = Base64.getUrlDecoder().decode(parts[1]);
        JsonNode claims = new ObjectMapper().readTree(payload);
        JsonNode exp = claims.get("exp");
        if (exp == null || !exp.isIntegralNumber() || !exp.canConvertToLong()) {
            throw new IllegalArgumentException("Fixture must contain numeric exp");
        }
        return exp.longValue();
    }

    @Test
    void expiredTokenIsRejectedWhileFreshTokenWorks() throws Exception {
        String oldToken = KubernetesAccessIT.token("EXPIRED_TOKEN_FILE");
        long exp = expiration(oldToken);

        // Runner và API server phải đồng bộ thời gian trong biên đã công bố.
        assertTrue(Instant.now().getEpochSecond() >= exp + 30,
                "Fixture has not passed its expiration boundary");

        HttpClient client = KubernetesAccessIT.client(
                Path.of(KubernetesAccessIT.env("KUBE_CA_FILE")));

        // READER_TOKEN_FILE phải vừa được cấp lại trước giai đoạn này.
        assertEquals(200, KubernetesAccessIT.getWithToken(
                client,
                KubernetesAccessIT.token("READER_TOKEN_FILE")).statusCode());

        assertEquals(401, KubernetesAccessIT.getWithToken(
                client, oldToken).statusCode());
    }
}
~~~

Trước giai đoạn cuối, cấp lại token reader để ca dương không dùng token cũng đã hết hạn:

~~~bash
k -n "$NS" create token sck-reader --duration=20m \
  > "$FIXTURES/reader.jwt"
~~~

Việc giải mã payload không xác minh chữ ký JWT. Bằng chứng nguồn gốc của fixture là token được cấp bởi cluster kiểm thử và **chính chuỗi token đó** từng được API server chấp nhận trước khi hết hạn. Bộ điều phối có thể so sánh checksum tệp để phát hiện tệp bị ghi đè giữa hai giai đoạn.

Biên 30 giây trong ví dụ là giả định kiểm thử, không phải quy định dung sai chung của mọi API server. Đồng bộ đồng hồ runner và cluster; nếu môi trường có dung sai khác, công bố và điều chỉnh biên tương ứng.

### 8.3. Những cách tạo ca hết hạn không hợp lệ

- Sửa `exp` trong payload mà không ký lại: chữ ký không còn đúng; đây là ca JWT bị sửa.
- Gửi chuỗi `expired-token`: đây là credentials không hợp lệ, không chứng minh hành vi hết hạn.
- Xóa ServiceAccount hoặc đối tượng ràng buộc rồi nhận `401`: đây là ca vô hiệu hóa token, khác với hết hạn tự nhiên.
- Dùng token có audience sai: đây là ca audience mismatch.
- Thay `Clock` trong JVM của test rồi gọi cluster: API server vẫn dùng thời gian của nó.
- Dùng `kubectl --as` thay cho Bearer token: impersonation không chứng minh token đã được xác minh.
- Để client tự lấy token mới trong ca “token cũ bị từ chối”: kết quả thành công lúc đó không phản ánh token cũ.

Các ca token sai chữ ký, sai audience và thiếu token vẫn hữu ích, nhưng cần tên và tiền điều kiện riêng.

### 8.4. Kiểm thử xoay token là một ca khác

Với projected ServiceAccount token, kubelet thay token trong volume trước khi nó hết hạn. Ứng dụng cần sử dụng được credentials mới theo cơ chế của client đang chọn; xem [Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).

Ca kiểm thử phục hồi nên giữ **một tiến trình ứng dụng** và thực hiện:

1. Khởi động Pod bằng ServiceAccount có đủ quyền, dùng projected token theo đường triển khai thực tế.
2. Xác nhận ứng dụng đọc được marker `baseline-v1`.
3. Chờ token trên volume đổi theo lịch thực tế; không suy thời điểm hết hạn chỉ từ `expirationSeconds` yêu cầu.
4. Sau mốc token cũ hết hạn, buộc ứng dụng tạo request mới; với watch, đóng kết nối thử nghiệm rồi yêu cầu kết nối lại.
5. Cập nhật ConfigMap thành `after-rotation-v2` và xác nhận ứng dụng đọc được giá trị mới.
6. Kiểm tra không có chuỗi lỗi `401` kéo dài, không cần khởi động lại và không có sự gia tăng request vô hạn.

Không chỉ quan sát “file token đã đổi”: điều đó chưa chứng minh client ngừng dùng token cũ. Ngược lại, một watch dài vẫn hoạt động cũng chưa chứng minh request xác thực mới đã thành công.

Nếu ứng dụng tự đọc file token, cần mở lại đường dẫn khi lấy credentials mới để nhận nội dung sau lần thay volume; không giữ mãi dữ liệu đọc lần đầu hoặc file descriptor của bản cũ. Không mount token bằng `subPath` trong ca cần nhận cập nhật. Với client thư viện, kiểm tra cơ chế refresh của đúng phiên bản và đường cấu hình đang sử dụng.

## 9. Kiểm thử chứng chỉ server không hợp lệ

### 9.1. Mỗi ca chỉ thay một điều kiện

Để phân biệt nguyên nhân, dựng HTTPS server cục bộ hoặc API endpoint kiểm thử riêng có chứng chỉ được kiểm soát. Không thay chứng chỉ của control plane đang phục vụ công việc khác.

| Ca TLS | CA trong client | Chứng chỉ server | Địa chỉ client dùng | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Dương | CA A | Còn hạn, CA A ký, SAN `localhost` | `https://localhost:<port>` | Handshake và HTTP thành công |
| Sai CA | Chỉ CA B | Giữ nguyên chứng chỉ của ca dương | Giữ nguyên | Lỗi xác minh trust chain |
| Sai SAN | CA A | Còn hạn, CA A ký, chỉ có SAN `wrong.test` | `https://localhost:<port>` | Lỗi xác minh hostname |
| Hết hạn | CA A | CA A ký, SAN `localhost`, `notAfter` trong quá khứ | Giữ nguyên | Lỗi kiểm tra thời hạn |
| Chưa có hiệu lực | CA A | CA A ký, SAN `localhost`, `notBefore` trong tương lai | Giữ nguyên | Lỗi kiểm tra thời hạn |

Fixture phải tạo CA A, CA B độc lập; CA còn hạn; chứng chỉ server có mục đích `serverAuth` và thuật toán được JDK của dự án chấp nhận. Nếu thuật toán bị JDK chặn, ca sẽ thất bại vì thuật toán thay vì điều kiện muốn kiểm tra.

Với ca sai SAN, không chỉ đổi URL sang hostname không tồn tại: khi DNS thất bại, TLS chưa diễn ra. Dùng `localhost` và chứng chỉ có SAN cố ý khác để đảm bảo kết nối đến đúng server rồi mới thất bại ở bước xác minh tên.

Chứng chỉ CA, thời hạn và danh tính endpoint là các khía cạnh của PKI cần được cấu hình riêng; xem [PKI certificates and requirements](https://kubernetes.io/docs/setup/best-practices/certificates/).

### 9.2. Tạo nhanh cặp CA và chứng chỉ cho ca dương

Ví dụ Bash/OpenSSL này dùng [openssl req](https://docs.openssl.org/3.5/man1/openssl-req/) và [openssl x509](https://docs.openssl.org/3.5/man1/openssl-x509/) để tạo vật liệu **chỉ dành cho kiểm thử** trong thư mục riêng. Mật khóa riêng không được đưa vào repository hay artifact công khai.

~~~bash
umask 077
TLS_FIXTURES="$(mktemp -d)"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$TLS_FIXTURES/ca-a.key" \
  -out "$TLS_FIXTURES/ca-a.crt" \
  -days 2 -sha256 \
  -subj "/CN=SCK Test CA A" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"

openssl req -newkey rsa:2048 -nodes \
  -keyout "$TLS_FIXTURES/server.key" \
  -out "$TLS_FIXTURES/server.csr" \
  -subj "/CN=localhost"

cat > "$TLS_FIXTURES/server.ext" <<'EXT'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost
EXT

openssl x509 -req \
  -in "$TLS_FIXTURES/server.csr" \
  -CA "$TLS_FIXTURES/ca-a.crt" \
  -CAkey "$TLS_FIXTURES/ca-a.key" \
  -CAcreateserial \
  -out "$TLS_FIXTURES/server.crt" \
  -days 1 -sha256 \
  -extfile "$TLS_FIXTURES/server.ext"

openssl pkcs12 -export \
  -inkey "$TLS_FIXTURES/server.key" \
  -in "$TLS_FIXTURES/server.crt" \
  -certfile "$TLS_FIXTURES/ca-a.crt" \
  -out "$TLS_FIXTURES/server.p12" \
  -passout pass:changeit

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$TLS_FIXTURES/ca-b.key" \
  -out "$TLS_FIXTURES/ca-b.crt" \
  -days 2 -sha256 \
  -subj "/CN=SCK Test CA B" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
~~~

Mật khẩu `changeit` ở đây chỉ dành cho keystore dùng một lần trong test. Tạo fixture mới cho mỗi job để ca dương không vô tình hết hạn.

Để tạo ca sai SAN, phát hành một chứng chỉ khác với `subjectAltName=DNS:wrong.test` nhưng giữ nguyên CA A và thời hạn hợp lệ. Với ca hết hạn/chưa có hiệu lực, dùng công cụ phát hành chứng chỉ cho phép đặt tường minh `notBefore/notAfter`, chẳng hạn chế độ `openssl ca` hoặc thư viện chứng chỉ trong test harness. Đọc lại các trường này trước khi chạy; lệnh `-days 1` ở trên không tạo chứng chỉ hết hạn.

### 9.3. Chạy phép thử sai CA bằng HTTPS server thật

Ví dụ sau khởi động HTTPS server cục bộ bằng [JDK HttpsServer](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html), dùng keystore vừa tạo và đếm request HTTP đã đi vào handler. Client dùng CA B nên phải thất bại trước khi handler nhận request.

Thiết lập:

- `TLS_SERVER_P12` trỏ đến `server.p12`.
- `TLS_GOOD_CA_FILE` trỏ đến `ca-a.crt`.
- `TLS_BAD_CA_FILE` trỏ đến `ca-b.crt`.
- Tệp chứa khóa server chỉ dùng cho lớp test này.

~~~java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import org.junit.jupiter.api.Test;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class KubernetesTlsIT {

    @Test
    void unknownCaIsRejectedBeforeHttpHandler() throws Exception {
        char[] password = "changeit".toCharArray();
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(
                Path.of(KubernetesAccessIT.env("TLS_SERVER_P12")))) {
            keys.load(in, password);
        }

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, password);
        SSLContext serverTls = SSLContext.getInstance("TLS");
        serverTls.init(kmf.getKeyManagers(), null, null);

        AtomicInteger handled = new AtomicInteger();
        HttpsServer server = HttpsServer.create(
                new InetSocketAddress("localhost", 0), 0);
        server.setHttpsConfigurator(new HttpsConfigurator(serverTls));
        server.createContext("/probe", exchange -> {
            handled.incrementAndGet();
            try {
                exchange.sendResponseHeaders(200, -1);
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            URI uri = URI.create("https://localhost:"
                    + server.getAddress().getPort() + "/probe");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpClient good = KubernetesAccessIT.client(
                    Path.of(KubernetesAccessIT.env("TLS_GOOD_CA_FILE")));
            assertEquals(200, good.send(
                    request, HttpResponse.BodyHandlers.discarding()).statusCode());
            assertEquals(1, handled.get());

            HttpClient bad = KubernetesAccessIT.client(
                    Path.of(KubernetesAccessIT.env("TLS_BAD_CA_FILE")));
            assertThrows(SSLHandshakeException.class, () ->
                    bad.send(request, HttpResponse.BodyHandlers.discarding()));

            // Chỉ request của ca dương được xử lý.
            assertEquals(1, handled.get());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Với dự án dùng module Java, test cần đọc module `jdk.httpserver`. Đưa fixture hết hạn và sai SAN vào cùng harness bằng cách thay keystore server, giữ đúng CA tin cậy tương ứng.

Trong test dùng trực tiếp JDK client ở trên, kỳ vọng `SSLHandshakeException` là cụ thể. Khi chạy bằng Fabric8, Kubernetes Java Client hoặc Spring, ngoại lệ có thể bị bọc; hãy tìm nguyên nhân trong cause chain và phân loại thành lỗi TLS. Không viết `assertThrows(Exception.class, ...)`, vì nó cũng chấp nhận lỗi thiếu file fixture, sai mật khẩu keystore hoặc DNS. Ý nghĩa ngoại lệ được mô tả trong [JDK SSLHandshakeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html).

Handler không nhận request không có nghĩa là không có bất kỳ dữ liệu mạng nào: TLS handshake vẫn trao đổi bản tin. Assertion này chỉ chứng minh không có request HTTP nào đi tới handler sau kết nối TLS bị từ chối.

### 9.4. Cấm đường tắt làm mất ý nghĩa phép thử

Không dùng `curl -k`, `insecure-skip-tls-verify`, trust-all `X509TrustManager` hoặc tắt hostname verification trong cấu hình client đang kiểm thử.

Không chuyển sang HTTP khi HTTPS thất bại. Không dùng CA đúng để “sửa” ca sai CA trước khi đã kiểm tra điều kiện từ chối. Sau phần âm, mới chạy ca phục hồi bằng CA/chứng chỉ đúng và xác nhận request thành công.

Một proxy fault injection kết thúc TLS có thể hữu ích, nhưng lúc đó client kiểm tra chứng chỉ của proxy. Chỉ báo cáo bằng chứng cho đúng đoạn kết nối đó; không nói đã xác minh chứng chỉ trực tiếp của API server.

## 10. Nối các fixture với ứng dụng Spring Cloud Kubernetes

### 10.1. Kiểm thử ConfigMap bắt buộc lúc khởi động

Ví dụ cấu hình chủ đích cho profile tích hợp:

~~~yaml
spring:
  application:
    name: catalog-service
  cloud:
    kubernetes:
      config:
        enabled: true
        name: catalog-service
        namespace: sck-auth-it
        fail-fast: true
        retry:
          enabled: false
~~~

Thay namespace bằng namespace động của lần chạy qua cơ chế cấu hình test. Cấu hình này chỉ minh họa chính sách lỗi khi nạp ConfigMap; dự án vẫn phải dùng cách kích hoạt Kubernetes Config Data hoặc bootstrap phù hợp với phiên bản đang chọn.

`spring.cloud.kubernetes.config.fail-fast=true` yêu cầu khởi động thất bại khi tải ConfigMap qua API gặp lỗi. Tắt retry ở ca khởi động giúp xác định thời gian và số lần thử. Khi kiểm tra retry, bật cơ chế và dependencies đúng phiên bản một cách tường minh, rồi kiểm tra tổng số lần cùng ngân sách thời gian. Xem [Using a ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Thực hiện ba lần chạy độc lập:

1. **Ca dương:** Pod dùng `sck-reader`, CA đúng; ứng dụng khởi động và đọc được `baseline-v1`.
2. **Ca thiếu quyền:** cùng image và nguồn cấu hình, Pod dùng `sck-no-access`; ứng dụng không đạt trạng thái phục vụ trong thời hạn đã đặt, có lỗi nguồn gốc `403`.
3. **Ca token hết hạn hoặc CA sai:** cấu hình đúng client để dùng fixture tường minh; ứng dụng thất bại với nguyên nhân `401` hoặc TLS tương ứng.

Việc truyền fixture token/CA cho client phụ thuộc backend. Hãy dùng API cấu hình hoặc cơ chế injection được hỗ trợ của đúng client, đồng thời vô hiệu hóa nguồn credentials thay thế trong test. Không giả định một thuộc tính token có cùng tác dụng với mọi starter.

Không bật `optional` cho nguồn cấu hình bắt buộc chỉ để context khởi động. Không chấp nhận “Spring context chạy được” làm kết quả duy nhất: ca dương phải xác nhận marker được đọc **từ Kubernetes**, không phải từ `application-test.yml` hoặc biến môi trường trùng tên.

### 10.2. Kiểm thử discovery, LoadBalancer và watch khi đang chạy

Chuẩn bị hai phiên bản ConfigMap, `baseline-v1` và `after-recovery-v2`, cùng một dịch vụ thử nghiệm có instance xác định. Sau baseline:

1. Gây lỗi ở workload thực sự gọi Kubernetes API.
2. Buộc đọc mới hoặc mở lại watch; tránh kết quả hoàn toàn từ cache.
3. Quan sát đúng lỗi, trạng thái đồng bộ và hành vi request nghiệp vụ.
4. Khôi phục đúng nguyên nhân: quyền bị thiếu, credentials mới hoặc CA/chứng chỉ hợp lệ.
5. Cập nhật dữ liệu thử nghiệm rồi xác nhận ứng dụng nhận được **giá trị mới**, không chỉ tiếp tục trả giá trị đã cache.
6. Với LoadBalancer, kiểm tra cả instance được chọn và request thực sự tới backend đó.

Nếu ứng dụng dùng discovery qua DiscoveryServer, lỗi RBAC thường cần được gây ở ServiceAccount của DiscoveryServer. Nếu dùng Configuration Watcher độc lập, sửa RBAC của watcher và quan sát cả đường watcher → ứng dụng; sửa ServiceAccount của ứng dụng chưa chắc tác động tới watch.

Nếu kết nối cũ vẫn mở hoặc cache còn hạn, chưa thể kết luận quyền mới đã có hiệu lực. Cho phép thời gian hội tụ có giới hạn và tạo request mới để kiểm tra. Với sự kiện watch, phân biệt việc mở watch bị `403` với lỗi xuất hiện trong stream hoặc kết nối bị đóng sau khi đã mở thành công.

### 10.3. Readiness và liveness

Mất quyền đọc Kubernetes API không tự động đồng nghĩa tiến trình bị treo. Trong hợp đồng của ứng dụng:

- **Startup:** ứng dụng chỉ hoàn tất khởi tạo khi nạp được cấu hình bắt buộc.
- **Readiness:** phản ánh khả năng phục vụ an toàn với dữ liệu hiện có và giới hạn tuổi dữ liệu đã đặt.
- **Liveness:** phản ánh tình trạng sống của tiến trình theo thiết kế; không gắn mọi lỗi phụ thuộc ngoài vào liveness gây vòng restart.
- **Recovery:** khi lỗi được sửa, xác nhận dữ liệu và readiness trở lại đúng trạng thái mà không cần cấp quyền rộng hơn.

Đối với ca fail-fast lúc khởi động, Pod có thể bị restart bởi Kubernetes. Assertion phải có deadline tổng và ghi nhận exit reason/log đã che dữ liệu; không chờ đến khi rollout timeout rất dài mới biết phép thử thất bại.

## 11. Retry, log và bằng chứng kiểm thử

### 11.1. Kiểm tra retry theo nguyên nhân

| Nguyên nhân | Điều cần xác nhận |
| --- | --- |
| `403` do thiếu RBAC | Không tạo vòng request dày đặc; quyền sai không được “sửa” bằng cách nâng lên cluster-admin |
| `401` do token cũ | Không retry vô hạn cùng chuỗi token; chỉ tiếp tục theo cơ chế refresh được hỗ trợ và có giới hạn |
| CA/SAN/thời hạn chứng chỉ sai | Không fallback sang bỏ kiểm tra TLS |
| Lỗi mạng tạm thời | Retry/backoff theo chính sách riêng, vẫn có timeout mỗi lần và deadline tổng |

Nếu số lần gọi tối đa là `N`, timeout mỗi request là `T` và các khoảng chờ lần lượt là `b1 ... b(N-1)`, ngân sách cơ bản cần xét là:

~~~text
N × T + tổng các khoảng chờ + chi phí khởi tạo/lập lịch
~~~

Không đặt deadline test bằng đúng một timeout request khi client có nhiều lần retry. Đếm request tại mock server hoặc bằng khả năng quan sát của môi trường test; không suy số lần retry chỉ từ số dòng log.

### 11.2. Dữ liệu được phép ghi trong kết quả

Một kết quả có ích gồm tên ca, namespace kiểm thử, ServiceAccount, loại resource, verb, lớp lỗi, số lần gọi, thời gian và trạng thái phục hồi. Với lỗi HTTP, có thể ghi status code và reason đã lọc.

Không ghi:

- `Authorization` header, nguyên JWT hay nội dung kubeconfig.
- Giá trị Secret, khóa riêng hoặc toàn bộ body phản hồi chứa cấu hình.
- Toàn bộ cấu hình client nếu `toString()` có thể chứa token hoặc password.

Trong test, kiểm tra chính đầu ra log/trace đã capture để phát hiện token hoặc giá trị Secret mẫu bị lộ. Các nhãn metric nên có tập giá trị nhỏ, chẳng hạn `authn`, `authz`, `tls`, `network`; tránh dùng JWT, URI động hoặc toàn bộ exception message làm nhãn.

API audit log chỉ là bằng chứng bổ sung nếu cluster kiểm thử cho phép truy cập. Ca TLS bị từ chối phía client có thể chưa tạo yêu cầu HTTP tới API server, nên không yêu cầu mọi lỗi TLS phải có audit event của resource.

## 12. Tổ chức pipeline và dọn tài nguyên

| Nhóm | Nơi chạy phù hợp | Bằng chứng chính |
| --- | --- | --- |
| Phân loại lỗi, retry, log masking | Mỗi lần sửa mã | Logic ứng dụng có giới hạn và không lộ credentials |
| RBAC `403` và ca dương `200` | Job tích hợp với cluster kiểm thử | Quyền thật và credentials mục tiêu |
| CA sai, SAN sai, chứng chỉ hết hạn | Job tích hợp với HTTPS harness | TLS thực sự từ chối điều kiện sai |
| JWT hết hạn theo thời gian thật | Job dài có cùng cluster xuyên suốt ca | Token từng hợp lệ bị từ chối sau `exp` |
| Projected token rotation và reconnect | Job lifecycle riêng | Tiến trình lâu dài tiếp tục hoạt động với token mới |
| Phục hồi discovery/watcher/LoadBalancer | Job tích hợp ứng dụng | Dữ liệu mới tới được hành vi nghiệp vụ |

Mỗi job dùng namespace, thư mục fixture và cổng HTTPS riêng. Không dùng một RoleBinding chung rồi để các bài kiểm thử chạy song song thu hồi quyền của nhau. Khi đổi phiên bản Kubernetes client hoặc cách nạp cấu hình, chạy lại những ca liên quan tới credentials, watch và TLS.

Khối `finally` hoặc bước cleanup của CI phải xóa đúng namespace được tạo bởi lần chạy, token fixture, keystore và khóa riêng trong thư mục tạm. Kiểm tra tên namespace, nhãn run-id và đường dẫn fixture thuộc lần chạy trước khi dọn; không dùng lệnh xóa toàn cluster hoặc wildcard mơ hồ.

Nếu setup thất bại vì bootstrap không có quyền tạo RoleBinding, thiếu CA hay server HTTPS không khởi động, đánh dấu **lỗi hạ tầng/fixture**, không đánh dấu negative test đã pass. Một ca không được chạy vì thiếu điều kiện phải hiện rõ trong báo cáo.

## 13. Bài thực hành và tiêu chí hoàn thành

Thực hiện theo thứ tự để mỗi ca âm có đối chứng:

1. Tạo namespace và hai ServiceAccount; xác nhận reader đọc được marker còn no-access nhận `403`.
2. Thay Role của một fixture riêng thành chỉ `get`, rồi kiểm tra request danh sách bị từ chối.
3. Cấp token có thời hạn, ghi nhận baseline `200`, chờ qua `exp` và xác nhận `401`; token mới cùng ServiceAccount phải nhận `200`.
4. Chạy HTTPS harness với CA đúng rồi CA sai; handler chỉ nhận request của ca dương.
5. Bổ sung chứng chỉ sai SAN và chứng chỉ hết hạn; xác nhận từng ca chỉ thay một điều kiện.
6. Chạy ứng dụng Spring thật với ConfigMap bắt buộc và fail-fast, kiểm tra nguyên nhân khi khởi động thất bại.
7. Tạo lỗi khi watcher hoặc discovery đang hoạt động; khôi phục rồi xác nhận phiên bản cấu hình/instance mới thực sự được sử dụng.
8. Thu log đã che dữ liệu và dọn toàn bộ tài nguyên của lần chạy.

Bài thực hành đạt yêu cầu khi các kết luận có bằng chứng riêng: **quyền thiếu bị từ chối đúng**, **token thực sự hết hạn bị từ chối**, **TLS vẫn xác minh chứng chỉ**, và **ứng dụng phục hồi đúng hợp đồng**. Việc thêm quyền rộng hoặc tắt xác minh chứng chỉ để tất cả test chuyển xanh là dấu hiệu ca kiểm thử đã mất mục tiêu.
