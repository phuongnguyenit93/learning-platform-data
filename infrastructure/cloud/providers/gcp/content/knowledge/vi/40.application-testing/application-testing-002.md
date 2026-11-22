# Tách lớp truy cập Google Cloud để kiểm thử ứng dụng Java

## 1. Vì sao cần tách lớp truy cập Google Cloud?

Một dịch vụ Java chạy trên Cloud Run, GKE hoặc Compute Engine thường phải truy cập Cloud Storage, Pub/Sub, Secret Manager, Firestore, BigQuery hoặc Cloud SQL. Nếu lớp xử lý nghiệp vụ trực tiếp tạo client Google Cloud, lấy Application Default Credentials (ADC), gọi API và diễn giải mã lỗi, một bài unit test đơn giản có thể vô tình cần mạng, project, quota, IAM hoặc thông tin xác thực thật.

Ví dụ, một `ReportService` có nhiệm vụ tạo báo cáo nhưng lại gọi trực tiếp `StorageOptions.getDefaultInstance().getService()` trong mỗi method. Để kiểm tra quy tắc “báo cáo rỗng phải bị từ chối”, test có thể phải khởi tạo SDK và phụ thuộc vào môi trường cloud. Test trở nên chậm, khó tái lập và đôi khi ghi dữ liệu vào bucket thật.

Giải pháp là **đặt một ranh giới rõ giữa nghiệp vụ và dịch vụ bên ngoài**:

- Logic nghiệp vụ chỉ biết các thao tác có ý nghĩa đối với ứng dụng như lưu báo cáo, tìm báo cáo, phát sự kiện hay đọc cấu hình.
- Adapter Google Cloud chuyển các thao tác đó thành lời gọi SDK.
- Unit test thay adapter bằng fake hoặc mock chạy hoàn toàn trong bộ nhớ.
- Integration test kiểm tra adapter thật với emulator khi khả dụng hoặc với tài nguyên thử nghiệm được cô lập.

Trong phạm vi `CLOUD_PROVIDERS_GCP`, tư duy này giúp kiểm thử ứng dụng Java khi dùng Storage, IAM, VPC, Compute Engine, GKE, Cloud Run, cơ sở dữ liệu, CI/CD và các yêu cầu độ tin cậy. Mục tiêu là có test nhanh cho nghiệp vụ và vẫn kiểm tra những rủi ro tích hợp như quyền IAM, network, quota, serialization và retry trước khi triển khai.

## 2. Nguyên tắc thiết kế: ports and adapters

### 2.1. Luồng phụ thuộc mong muốn

Một mô hình phù hợp là **ports and adapters** (còn gọi là kiến trúc hexagonal). Port là interface do ứng dụng sở hữu. Adapter hiện thực port bằng SDK hoặc một công nghệ cụ thể. Application service nhận port qua constructor, nhờ đó không cần biết Cloud Storage dùng lớp `Storage` nào, Pub/Sub dùng publisher nào hoặc cơ sở dữ liệu nằm trên Cloud SQL hay local.

~~~mermaid
flowchart LR
    C[HTTP controller hoặc scheduled job] --> S[Application service]
    S --> P[Port: ReportStore]
    P --> G[GCS adapter]
    G --> SDK[Google Cloud Storage Java SDK]
    SDK --> CLOUD[(Cloud Storage)]

    P -. test wiring .-> F[In-memory fake / Mockito mock]
    F -. không có network .-> T[Unit hoặc component test]
~~~

Mũi tên phụ thuộc trong mã nguồn đi từ nghiệp vụ đến **interface do nghiệp vụ định nghĩa**, trong khi adapter phụ thuộc vào interface đó. SDK nằm ở lớp ngoài. Phần cấu hình Spring quyết định sử dụng adapter nào tùy môi trường.

Nếu cần thay Cloud Storage bằng một hệ thống khác, phần nghiệp vụ thường không phải sửa. Nếu cần kiểm thử một trường hợp thất bại, test điều khiển hành vi của port mà không phải ép SDK phát sinh lỗi thật.

### 2.2. Những thứ nên và không nên đi qua port

| Nên xuất hiện trong port | Nên giữ trong adapter |
|---|---|
| `saveReport(reportId, bytes)` | Tên bucket, object path, `BlobInfo` |
| `findReport(reportId)` | `Storage.get(...)`, `Blob.getContent()` |
| `publishOrderCreated(event)` | Pub/Sub topic name, `Publisher`, message attributes |
| `getPaymentConfiguration()` | Secret Manager version path, client call |
| `loadCustomer(customerId)` | SQL query, Firestore document path |
| Ngoại lệ theo nghĩa nghiệp vụ | `StorageException`, `ApiException`, gRPC status |

Không đưa các kiểu của Google Cloud SDK như `Blob`, `PubsubMessage`, `DocumentSnapshot` hoặc `ApiException` vào API nghiệp vụ nếu không có lý do rõ ràng. Nếu port trả về một SDK type, unit test vẫn phải hiểu SDK đó và lớp nghiệp vụ bị khóa vào một nhà cung cấp.

Ngược lại, không cần tạo interface cho từng method đơn giản của một thư viện chỉ để “có interface”. Port nên thể hiện **ý định nghiệp vụ**, có ít phương thức nhất đủ phục vụ use case, và tránh biến thành bản sao tổng quát của SDK.

## 3. Ví dụ xuyên suốt: dịch vụ lưu và đọc báo cáo

Giả sử ứng dụng Spring Boot tạo báo cáo dạng văn bản rồi lưu vào Cloud Storage. Yêu cầu nghiệp vụ là:

1. ID của báo cáo chỉ gồm chữ, số, dấu gạch nối hoặc gạch dưới; độ dài 1–64 ký tự.
2. Nội dung sau khi loại bỏ khoảng trắng ở hai đầu không được rỗng.
3. Báo cáo được tạo một lần; không ghi đè báo cáo cùng ID.
4. Có thể đọc lại báo cáo theo ID; báo cáo không tồn tại được chuyển thành một lỗi nghiệp vụ rõ ràng.

Chúng ta sẽ tách ba phần: `ReportStore`, `ReportService` và `GcsReportStore`.

### 3.1. Port do ứng dụng sở hữu

~~~java
import java.util.Optional;

public interface ReportStore {
    void create(String reportId, byte[] content);

    Optional<byte[]> find(String reportId);
}
~~~

Interface này không import Google Cloud SDK. `Optional.empty()` có nghĩa báo cáo chưa tồn tại. Contract cần được ghi rõ: `create` không ghi đè đối tượng đã có; `find` trả về dữ liệu của báo cáo, không trả metadata SDK. Khi ứng dụng cần version hoặc checksum, bổ sung một model nội bộ có những thuộc tính thực sự cần thiết.

### 3.2. Logic nghiệp vụ không biết Cloud Storage

~~~java
import java.nio.charset.StandardCharsets;
import java.util.NoSuchElementException;
import java.util.Objects;

public final class ReportService {
    private final ReportStore reports;

    public ReportService(ReportStore reports) {
        this.reports = Objects.requireNonNull(reports);
    }

    public void create(String reportId, String content) {
        validateId(reportId);
        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException("Report content is empty");
        }

        reports.create(
            reportId,
            content.strip().getBytes(StandardCharsets.UTF_8)
        );
    }

    public String read(String reportId) {
        validateId(reportId);

        byte[] bytes = reports.find(reportId)
            .orElseThrow(
                () -> new NoSuchElementException("Report not found")
            );

        return new String(bytes, StandardCharsets.UTF_8);
    }

    private static void validateId(String reportId) {
        if (reportId == null ||
            !reportId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid report ID");
        }
    }
}
~~~

`ReportService` chỉ có quy tắc validate ID, chuẩn hóa nội dung và xử lý báo cáo chưa tồn tại. Nó không có dependency vào `StorageOptions`, `BlobId` hay ADC. Không có câu lệnh nào ở đây phải kết nối Internet.

Trong hệ thống lớn, có thể tạo ngoại lệ chuyên biệt như `ReportNotFoundException` và `ReportAlreadyExistsException` để controller ánh xạ lần lượt sang HTTP 404 hoặc 409. Ví dụ dùng `NoSuchElementException` và `IllegalArgumentException` để tập trung vào ranh giới kiểm thử.

### 3.3. Adapter triển khai bằng Cloud Storage

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

import java.util.Objects;
import java.util.Optional;

public final class GcsReportStore implements ReportStore {
    private final Storage storage;
    private final String bucket;

    public GcsReportStore(Storage storage, String bucket) {
        this.storage = Objects.requireNonNull(storage);
        this.bucket = Objects.requireNonNull(bucket);
    }

    @Override
    public void create(String reportId, byte[] content) {
        BlobId id = blobId(reportId);
        BlobInfo info = BlobInfo.newBuilder(id)
            .setContentType("text/plain; charset=utf-8")
            .build();

        storage.create(
            info,
            content,
            Storage.BlobTargetOption.doesNotExist()
        );
    }

    @Override
    public Optional<byte[]> find(String reportId) {
        Blob blob = storage.get(blobId(reportId));
        return blob == null
            ? Optional.empty()
            : Optional.of(blob.getContent());
    }

    private BlobId blobId(String reportId) {
        return BlobId.of(bucket, "reports/" + reportId + ".txt");
    }
}
~~~

Phần chuyển ID thành object path và chi tiết `BlobInfo` chỉ nằm trong adapter. Tùy chọn `doesNotExist()` dùng precondition để ngăn ghi đè object đã tồn tại; đây là biện pháp quan trọng khi thao tác create có thể bị lặp lại bởi retry hoặc nhiều instance.

Trong ứng dụng production, adapter nên chuyển `StorageException` của Google Cloud thành ngoại lệ do ứng dụng định nghĩa. Ví dụ:

- `404` ở thao tác đọc được biểu diễn bằng `Optional.empty()` nếu SDK trả về null.
- `412 Precondition Failed` ở thao tác tạo có thể được ánh xạ thành `ReportAlreadyExistsException`; nếu response trước bị mất, hãy đọc trạng thái object trước khi kết luận.
- `429`, `503` hoặc timeout là lỗi hạ tầng tạm thời; có thể được ánh xạ thành `ReportStoreUnavailableException` kèm cause và trạng thái retry phù hợp.

Việc ánh xạ lỗi nên giữ nguyên nguyên nhân (`cause`), mã lỗi có ích cho quan sát và khả năng phân loại retry. Không nuốt mọi lỗi rồi trả `Optional.empty()`: làm như vậy sẽ đánh đồng “không có báo cáo” với “không thể kết nối Cloud Storage”.

## 4. Cấu hình dependency injection trong Spring Boot

Adapter không nên tự tạo `Storage` bằng singleton static. Spring configuration có thể tạo client một lần và chuyển nó vào adapter qua constructor.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ReportConfiguration {
    @Bean
    @Profile("!test")
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }

    @Bean
    @Profile("!test")
    ReportStore reportStore(
        Storage storage,
        @Value("${app.reports.bucket}") String bucket
    ) {
        return new GcsReportStore(storage, bucket);
    }

    @Bean
    ReportService reportService(ReportStore store) {
        return new ReportService(store);
    }
}
~~~

Trong production, `StorageOptions` dùng ADC để tìm credential của môi trường. Nếu chạy trên Cloud Run hoặc GKE, ưu tiên dùng service account gắn với workload hoặc Workload Identity Federation thay vì lưu JSON key trong image. IAM cần cấp đúng quyền đọc/ghi trên bucket.

Trong test, profile `test` không tạo bean `Storage` hay `GcsReportStore`. Test tự cung cấp `ReportStore` giả. Như vậy việc khởi động Spring context cho test không phụ thuộc vào ADC và project Google Cloud.

Không đặt toàn bộ ứng dụng dưới profile `test` nếu profile đó làm mất các bean nghiệp vụ cần kiểm tra. Hãy dùng profile hoặc conditional configuration **cho riêng adapter ngoài hệ thống**. Với dự án dùng Spring Cloud GCP auto-configuration, cần kiểm tra các bean tự động được tạo; có thể tắt các auto-config không cần trong test.

## 5. Unit test với Mockito: kiểm tra quy tắc nghiệp vụ

### 5.1. Mục đích của mock

Mockito mock ghi nhận tương tác và có thể được lập trình để trả kết quả hoặc ném lỗi. Mock rất hữu ích khi test cần xác nhận:

- Dữ liệu hợp lệ dẫn đến đúng một lệnh ghi.
- Input sai bị chặn trước khi gọi dịch vụ bên ngoài.
- Kết quả “not found” được ánh xạ sang lỗi nghiệp vụ.
- Retry hoặc fallback không gọi thêm dependency ngoài ý muốn.

Trong unit test, chỉ cần khởi tạo `ReportService` và mock `ReportStore`; không cần Spring context, Google Cloud SDK credential, network hay emulator.

### 5.2. Unit test minh họa với JUnit 5 và Mockito

~~~java
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.NoSuchElementException;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.aryEq;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class ReportServiceTest {

    @Test
    void createStoresUtf8Bytes() {
        ReportStore store = mock(ReportStore.class);
        ReportService service = new ReportService(store);

        service.create("report-17", "  Xin chào  ");

        verify(store).create(
            eq("report-17"),
            aryEq("Xin chào".getBytes(StandardCharsets.UTF_8))
        );
        verifyNoMoreInteractions(store);
    }

    @Test
    void invalidIdDoesNotCallStore() {
        ReportStore store = mock(ReportStore.class);
        ReportService service = new ReportService(store);

        assertThrows(
            IllegalArgumentException.class,
            () -> service.create("../secrets", "valid content")
        );

        verifyNoInteractions(store);
    }

    @Test
    void missingReportIsReported() {
        ReportStore store = mock(ReportStore.class);
        when(store.find("missing")).thenReturn(Optional.empty());

        ReportService service = new ReportService(store);

        assertThrows(
            NoSuchElementException.class,
            () -> service.read("missing")
        );

        verify(store).find("missing");
    }
}
~~~

Các test này có thể chạy trên laptop không có `gcloud`, file key hoặc quyền Google Cloud. Chúng chỉ xác nhận quy tắc của `ReportService` và việc gọi port theo contract. Chúng **không** chứng minh adapter GCS truy cập đúng bucket, có IAM permission, xử lý 412 hay ghi đúng content type.

Nếu chỉ test `verify(store).create(...)`, ta dễ bỏ qua kết quả cuối cùng và hành vi tích hợp. Vì vậy cần bổ sung fake và kiểm thử adapter.

## 6. In-memory fake: kiểm tra hành vi qua nhiều lời gọi

### 6.1. Mock khác fake ở điểm nào?

Mock thường được điều khiển theo từng test và dùng để kiểm tra tương tác. **Fake** là implementation đơn giản nhưng có trạng thái thật, ví dụ một map trong bộ nhớ thay cho Cloud Storage. Fake phù hợp với component test hoặc kiểm tra nhiều use case nối tiếp mà không phải lập trình từng lời gọi.

Một fake tốt cần mô phỏng **hợp đồng cốt lõi** của port. Nếu production không cho ghi đè thì fake cũng không được ghi đè. Nếu ứng dụng yêu cầu ranh giới bất biến của byte array, fake nên sao chép dữ liệu để tránh test truyền mảng rồi vô tình chỉnh sửa trạng thái.

### 6.2. Cài đặt fake

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryReportStore implements ReportStore {
    private final Map<String, byte[]> data = new ConcurrentHashMap<>();

    @Override
    public void create(String reportId, byte[] content) {
        byte[] copy = Arrays.copyOf(content, content.length);
        if (data.putIfAbsent(reportId, copy) != null) {
            throw new IllegalStateException("Report already exists");
        }
    }

    @Override
    public Optional<byte[]> find(String reportId) {
        byte[] value = data.get(reportId);
        return value == null
            ? Optional.empty()
            : Optional.of(Arrays.copyOf(value, value.length));
    }
}
~~~

Vì mỗi test nên tạo instance fake riêng, trạng thái không bị rò rỉ giữa test. Nếu fake dùng chung giữa các test hoặc singleton Spring context, cần xóa dữ liệu hoặc thiết lập fixture cô lập trước từng test.

### 6.3. Component test qua public API của service

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ReportComponentTest {

    @Test
    void createThenReadReturnsNormalizedContent() {
        ReportStore fake = new InMemoryReportStore();
        ReportService service = new ReportService(fake);

        service.create("r001", "  Nội dung thử nghiệm  ");

        assertEquals("Nội dung thử nghiệm", service.read("r001"));
        assertThrows(
            IllegalStateException.class,
            () -> service.create("r001", "ghi đè")
        );
    }
}
~~~

Test kiểm tra hành vi tạo, đọc và chống ghi đè mà không quan tâm class SDK. Nếu ngày mai adapter đổi từ Cloud Storage sang Firestore, test nghiệp vụ này vẫn có ý nghĩa.

Fake cần được kiểm tra bằng **contract tests** để tránh việc nó cư xử khác adapter thật ở những trường hợp quan trọng.

## 7. Test adapter Google Cloud riêng biệt

Ứng dụng đã tách port vẫn cần chắc rằng adapter chuyển lệnh đúng: tên bucket, object path, content type, precondition và kết quả không tồn tại. Có thể mock chính SDK ở lớp adapter để kiểm tra mapping mà không gọi API thật.

Ví dụ:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class GcsReportStoreTest {

    @Test
    void writesToConfiguredBucketWithCreateOnlyPrecondition() {
        Storage sdk = mock(Storage.class);
        GcsReportStore adapter = new GcsReportStore(sdk, "test-bucket");
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        adapter.create("r001", bytes);

        ArgumentCaptor<BlobInfo> info =
            ArgumentCaptor.forClass(BlobInfo.class);

        verify(sdk).create(
            info.capture(),
            same(bytes),
            any(Storage.BlobTargetOption.class)
        );

        assertEquals(
            BlobId.of("test-bucket", "reports/r001.txt"),
            info.getValue().getBlobId()
        );
        assertEquals(
            "text/plain; charset=utf-8",
            info.getValue().getContentType()
        );
    }

    @Test
    void missingObjectReturnsEmpty() {
        Storage sdk = mock(Storage.class);
        BlobId id = BlobId.of("test-bucket", "reports/r001.txt");

        when(sdk.get(id)).thenReturn(null);

        GcsReportStore adapter = new GcsReportStore(
            sdk, "test-bucket"
        );

        assertTrue(adapter.find("r001").isEmpty());
    }
}
~~~

Test trên kiểm tra adapter tạo đúng đường dẫn và content type. Với precondition, nên bổ sung kiểm tra giá trị option theo contract hoặc một integration test xác nhận thao tác tạo trùng bị từ chối. Không xem một lời gọi Mockito `any(...)` là bằng chứng phía server thật sự thực thi precondition.

Khi adapter phải ánh xạ `StorageException`, test các mã 412, 429, 403 và 5xx theo đúng chính sách; giữ mã lỗi hoặc cause cần thiết. Nếu mock SDK quá phức tạp vì phải dựng nhiều lớp response, ưu tiên test ở port boundary và kiểm tra phần SDK còn lại bằng integration test thay vì mô phỏng sâu cấu trúc nội bộ thư viện.

## 8. Kiểm thử Spring context mà không khởi tạo Google Cloud client

Mục tiêu của Spring component test là kiểm tra bean wiring, configuration và luồng gọi service/controller. Có thể dùng một `@TestConfiguration` cung cấp fake port trong profile `test`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    classes = {
        ReportConfiguration.class,
        ReportSpringTest.FakeConfiguration.class
    }
)
@ActiveProfiles("test")
class ReportSpringTest {

    @Autowired
    ReportService service;

    @Test
    void applicationServiceUsesInjectedFake() {
        service.create("spring-1", "  test Spring  ");
        assertEquals("test Spring", service.read("spring-1"));
    }

    @TestConfiguration
    static class FakeConfiguration {
        @Bean
        ReportStore reportStore() {
            return new InMemoryReportStore();
        }
    }
}
~~~

Ở profile `test`, hai bean production `Storage` và `GcsReportStore` không được tạo, nên Spring chỉ inject fake. Cần xác nhận cấu hình thật trong ứng dụng không có bean cloud khác được tạo bởi auto-configuration rồi cố truy cập ADC ngoài ý muốn.

Nếu test chỉ kiểm tra `ReportService`, không nên khởi động Spring context: unit test JUnit thông thường nhanh hơn. Chỉ dùng `@SpringBootTest` khi cần kiểm tra wiring, validation HTTP, security filters hoặc behavior ở mức component.

## 9. Lựa chọn mức kiểm thử phù hợp

Không có một loại test nào kiểm chứng được tất cả. Nên kết hợp các mức theo thời gian chạy và độ trung thực của môi trường.

| Loại kiểm thử | Dùng hạ tầng nào? | Kiểm chứng điều gì? | Không bảo đảm điều gì? |
|---|---|---|---|
| Unit test | Mockito mock hoặc stub | Quy tắc nghiệp vụ, validation, quyết định retry/fallback | Hành vi SDK, IAM và mạng |
| Component test | Fake port và Spring context | Bean wiring, HTTP/controller, luồng nhiều bước | Serialization/SDK thật |
| Adapter test | Mock SDK hoặc fake protocol | Chuyển đổi request/response, tên resource, precondition | Chính sách server thật |
| Contract test | Cùng bộ kiểm tra trên fake và adapter | Hành vi nhất quán theo contract | Toàn bộ tính năng cloud nếu chỉ dùng fake |
| Emulator integration | Emulator chính thức khi có | Một phần API, serialization và luồng client | IAM, quota, VPC, mọi hành vi production |
| Cloud integration | Project thử nghiệm và dịch vụ thật | API, credential, IAM, network và metadata thực | Tải production và data thật |
| End-to-end | Môi trường staging gần production | Hành trình người dùng và tương tác giữa service | Mọi tình huống tải/lỗi hiếm |

Thực tế, nên có nhiều test unit/component chạy trong mọi pull request, một số adapter/contract test trong pipeline thường xuyên, và các cloud integration/e2e test chạy ở staging hoặc trong job được kiểm soát.

## 10. Contract test: giữ fake và adapter cùng một hợp đồng

Fake trong bộ nhớ có thể vô tình khác adapter cloud. Ví dụ, fake cho phép ghi đè trong khi GCS adapter dùng precondition create-only; fake trả dữ liệu ngay lập tức nhưng cơ sở dữ liệu hoặc event system có thể nhất quán cuối cùng.

Một bộ contract test nên định nghĩa các hành vi có thể dùng chung:

1. Ghi một báo cáo mới rồi đọc lại đúng bytes.
2. Ghi trùng ID bị từ chối và không làm thay đổi bytes trước đó.
3. Tìm ID không tồn tại trả `Optional.empty()`.
4. Nội dung có ký tự Unicode được giữ nguyên.
5. Khi xảy ra lỗi không phải not-found, port báo lỗi thay vì trả “không tồn tại”.
6. Các key và ID có ràng buộc rõ ràng; hành vi đối với ID sai được thống nhất.

Chạy bộ kiểm tra trên `InMemoryReportStore` và trên một adapter nối tới môi trường tích hợp. Đối với backend hỗ trợ nhiều version, eventual consistency hoặc transaction, ghi rõ khác biệt không thể mô phỏng đơn giản; không kéo mọi đặc tính SDK vào contract nếu nghiệp vụ không sử dụng.

Cũng cần lưu ý fake ví dụ ném `IllegalStateException` khi báo cáo đã tồn tại, còn SDK có thể ném `StorageException` 412. **Đây chưa phải contract thống nhất.** Trước khi đưa vào production, adapter nên chuyển 412 thành `ReportAlreadyExistsException` và fake cũng ném cùng exception; sau đó contract test mới có thể kiểm tra chính xác cùng hành vi.

## 11. Khi nào dùng emulator, khi nào dùng tài nguyên GCP thật?

Không phải mọi Google Cloud service đều có emulator chính thức hoặc emulator bao phủ mọi API.

### 11.1. Emulator phù hợp

Một số emulator hữu ích:

- **Pub/Sub emulator:** kiểm thử luồng publish/subscribe cục bộ. Java client thường cần được cấu hình endpoint/channel và no-credentials rõ ràng; không mặc định mọi SDK tự chuyển sang emulator chỉ nhờ một environment variable.
- **Firestore emulator:** kiểm tra đọc/ghi document, transaction và một phần query mà emulator hỗ trợ.
- **Bigtable emulator:** thử nghiệm API đọc/ghi bảng trong môi trường không cần tài nguyên production.

Chạy emulator trong CI giúp có test tích hợp nhanh và tránh phát sinh chi phí gọi cloud thật. Tuy nhiên, emulator thường bỏ qua hoặc đơn giản hóa IAM, VPC, quota, latency, một số validation và hành vi backend. Kiểm tra tài liệu emulator của dịch vụ trước khi dựa vào một tính năng cụ thể.

**Cloud Storage không có một emulator chính thức với mức tương thích đầy đủ tương tự một số dịch vụ kể trên.** Có fake server bên thứ ba, nhưng cần xác minh mức tương thích với SDK, điều kiện generation, metadata, signed URL và lỗi. Một fake giao thức chỉ là một lớp kiểm thử bổ sung.

### 11.2. Dùng project thử nghiệm cho kiểm tra tích hợp

Các tình huống sau nên được kiểm tra với dịch vụ GCP thật trong project thử nghiệm:

- IAM, service account, Workload Identity Federation và ADC.
- Bucket policy, object generation, precondition, retention và encryption.
- API enablement, service agent, quota, rate limit, region và network.
- Pub/Sub acknowledgment, duplicate delivery, retry và dead-letter policy.
- Cloud SQL kết nối qua private IP, connector, TLS và failover.
- VPC Service Controls, organization policy và điều kiện IAM.

Project test phải có danh tính riêng, resource name riêng, billing/quota guardrails và cơ chế cleanup. Tránh sử dụng production project hoặc dữ liệu thật cho test. Những resource có lifecycle dài như Cloud SQL, GKE hay Spanner cần kế hoạch hủy/thu hồi riêng, tránh chi phí tồn đọng.

## 12. Thiết kế test cho Pub/Sub và luồng bất đồng bộ

Pub/Sub có khác biệt quan trọng với CRUD: publish và xử lý message có thể bất đồng bộ, giao nhận có thể lặp, ack deadline ảnh hưởng việc giao lại. Vì vậy, port nên phản ánh mục đích nghiệp vụ, ví dụ:

~~~java
public interface EventPublisher {
    void publishReportCreated(String reportId);
}
~~~

Adapter Pub/Sub chuyển sự kiện thành message, attributes và topic. Test nghiệp vụ có thể dùng một fake ghi danh sách event:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class RecordingPublisher implements EventPublisher {
    private final List<String> events = new ArrayList<>();

    @Override
    public void publishReportCreated(String reportId) {
        events.add(reportId);
    }

    public List<String> events() {
        return List.copyOf(events);
    }
}
~~~

Khi kiểm tra workflow, test xác nhận sự kiện chỉ phát sau bước lưu báo cáo thành công và có ID đúng. Integration test riêng với Pub/Sub emulator hoặc topic thử nghiệm xác minh serialization và subscription flow.

Không giả định một lần publish luôn dẫn đến đúng một lần xử lý. Hãy thiết kế consumer idempotent, chống xử lý trùng theo event ID hoặc business key, test retry/ack/nack và tình huống subscriber restart. Với yêu cầu giao dịch giữa database và Pub/Sub, cân nhắc outbox pattern thay vì phát message giữa transaction chưa commit.

## 13. Tách Secret Manager và configuration

Ứng dụng thường gọi Secret Manager để lấy API key, mật khẩu hoặc thông số bí mật. Tránh để service nghiệp vụ gọi trực tiếp `SecretManagerServiceClient`. Port có thể định nghĩa hành vi:

~~~java
public interface PaymentSecrets {
    String paymentGatewayToken();
}
~~~

Production adapter dùng Secret Manager và quy trình cache/refresh phù hợp. Unit test trả token giả, không phải secret thật. Không log token, secret payload hoặc access token.

Các điều cần kiểm tra riêng:

- Secret version đúng, ví dụ phiên bản cụ thể hay alias đã được phê duyệt.
- Không được phép truy cập secret thì báo lỗi khác “secret không tồn tại”.
- Rotation không làm ứng dụng giữ secret cũ vô hạn.
- Service account có quyền `roles/secretmanager.secretAccessor` trên đúng secret.
- Test không yêu cầu biến môi trường production hoặc service account key.

Không đưa logic đọc Secret Manager vào static initializer, constructor domain object hoặc method validate, vì điều đó khiến test nghiệp vụ cần credential ngay lúc khởi tạo.

## 14. Tách lớp dữ liệu Cloud SQL, Firestore và BigQuery

Cách áp dụng port phụ thuộc dạng dữ liệu:

- **Cloud SQL:** domain service phụ thuộc repository interface; adapter dùng JDBC/JPA hoặc thư viện truy cập dữ liệu. Unit test dùng fake repository; integration test có thể dùng Testcontainers với cùng engine và phiên bản database phù hợp. Kết nối Cloud SQL thật vẫn cần test riêng cho IAM, Cloud SQL connector/proxy, VPC và TLS.
- **Firestore:** port mô tả truy vấn theo nghĩa nghiệp vụ. Dùng Firestore emulator để thử serialization, transaction và truy vấn được hỗ trợ; kiểm tra index, security rules hoặc IAM ở môi trường tương ứng.
- **BigQuery:** port biểu diễn thao tác phân tích, ví dụ lấy tổng hợp doanh thu. Unit test thay client bằng dữ liệu cố định; integration test thật xác minh SQL dialect, schema, partition, quota và chi phí xử lý dữ liệu.
- **Spanner hoặc Bigtable:** không mô phỏng đơn giản các đặc tính transaction, consistency, partition hay scan bằng một map rồi xem là tương đương production.

Một repository interface quá chung kiểu `execute(String query)` có thể khiến nghiệp vụ phụ thuộc vào SQL hoặc syntax của backend. Ưu tiên phương thức thể hiện use case như `findActiveOrders(customerId)` hoặc `saveInvoice(invoice)`.

## 15. Kiểm thử lỗi, retry, timeout và idempotency

Tách port cho phép cố ý tạo lỗi mà không phải làm hỏng project thật. Những tình huống quan trọng:

| Tình huống | Mô phỏng trong test | Kết quả mong đợi |
|---|---|---|
| Resource không tồn tại | Fake trả `Optional.empty()` | Ứng dụng trả lỗi not-found rõ ràng |
| Không đủ quyền | Adapter/fake ném lỗi permission | Không retry vô hạn; ghi telemetry phù hợp |
| Quota 429 | Stub ném lỗi retryable | Backoff và giới hạn số lần retry |
| Backend 503 | Stub thất bại vài lần rồi thành công | Retry có giới hạn và không nhân đôi side effect |
| Deadline hết | Fake chậm có kiểm soát hoặc virtual clock | Hủy/thoát theo deadline |
| Create đã thành công nhưng response bị mất | Fake ghi thành công rồi ném lỗi | Đọc trạng thái, tránh tạo trùng |
| Hai request tạo cùng ID | Fake thread-safe với put-if-absent | Chỉ một request được tạo mới |
| Serialization lỗi | Adapter test với bytes/encoding bất thường | Không ghi object sai hoặc mất dữ liệu |

Không dùng `Thread.sleep()` trong unit test chỉ để chờ backoff. Nếu tự viết retry, hãy inject `Clock` hoặc interface `Sleeper/Scheduler` và fake thời gian trong test. Nếu dùng Google Cloud Java client có retry tự động, kiểm tra cấu hình `RetrySettings` ở adapter, sau đó kiểm thử hành vi end-to-end trong môi trường thích hợp mà không thêm nhiều tầng retry không kiểm soát.

Một fake đơn giản không chứng minh có bảo đảm transaction hay exactly-once trên cloud. Các tình huống liên quan side effect, race condition hoặc event ordering cần test chuyên biệt.

## 16. Kiểm soát dữ liệu test và tính tái lập

Test tốt phải độc lập với thứ tự chạy và trạng thái môi trường.

- Mỗi test tạo dữ liệu riêng; không dùng chung object name hoặc document ID với test khác.
- Dùng prefix có build ID hoặc UUID cho tài nguyên integration; xóa sau test và có cơ chế TTL/cleanup dự phòng.
- Không dùng giờ hệ thống trực tiếp trong logic khó test; inject `Clock` và dùng `Clock.fixed(...)` khi cần.
- Không dùng random không kiểm soát cho assertion; inject generator hoặc seed nếu có yêu cầu.
- Không chia sẻ fake state giữa test trừ khi chủ động kiểm soát lifecycle.
- Không phụ thuộc vào kết quả test trước hoặc dữ liệu đã tồn tại trong project.
- Không đưa PII, token, private key hoặc dữ liệu khách hàng vào fixture.
- Không dùng tài nguyên production để kiểm tra thao tác xóa, migration hoặc phân quyền.

Nếu test bất đồng bộ, chờ theo điều kiện có timeout hữu hạn thay vì sleep thời gian cố định. Nếu có event pipeline hoặc eventual consistency, dùng polling có giới hạn và assertion trên trạng thái cuối cùng.

## 17. Chạy test trong CI/CD trên GCP

Một pipeline thực tế nên tách ba nhóm công việc:

1. **Pull request nhanh:** compile, unit test, component test, lint và static analysis. Không cần credential Google Cloud; không được deploy hoặc sửa tài nguyên production.
2. **Integration test:** chạy emulator/Testcontainers hoặc project thử nghiệm. Nếu dùng project thật, job có danh tính riêng với quyền tối thiểu và chỉ chạy trên ref/trust level được phép.
3. **Release validation:** kiểm tra artifact, smoke test trên staging, hợp đồng API và các luồng quan trọng trước production promotion.

Cloud Build có thể chạy Maven hoặc Gradle trong container và cung cấp build log. Nếu CI nằm ngoài Google Cloud, ưu tiên Workload Identity Federation thay cho JSON key dài hạn. Service account của integration test chỉ cần quyền tạo/xóa/đọc đúng tài nguyên thử nghiệm, không cần Owner.

Ví dụ cấu trúc profile Maven mang tính tham khảo:

~~~text
mvn -B test                     # Unit/component tests, không cần GCP
mvn -B verify -Pintegration     # Integration tests do dự án cấu hình
~~~

Tên profile `integration` là quy ước dự án tự tạo, không phải Maven profile được cung cấp mặc định. Cấu hình Surefire/Failsafe hoặc công cụ tương đương cần tách test theo tag hoặc tên class. Trong STEP 4 này, các lệnh chỉ là ví dụ học thuật; không có thao tác build hoặc chạy test nào được thực hiện.

CI job dùng GCP thật cần kiểm tra:

- Environment variables trỏ đúng project, region, bucket/topic/database thử nghiệm.
- ADC hoặc WIF thể hiện đúng principal; tránh file key trong repository.
- Quyền IAM đủ dùng và kiểm tra được tình huống permission denied.
- Quota, billing và concurrency có giới hạn.
- Mọi tài nguyên tạo ra có dấu vết, cleanup và alert chi phí thích hợp.
- Log và report không chứa secret hay dữ liệu nhạy cảm.

## 18. Những lỗi thiết kế thường gặp

| Cách làm gây khó kiểm thử | Tác động | Cách cải thiện |
|---|---|---|
| Tạo SDK client bên trong mỗi method nghiệp vụ | Unit test phụ thuộc ADC và network | Inject port qua constructor |
| Service trả về `Blob` hoặc `DocumentSnapshot` | Domain bị khóa vào SDK | Dùng DTO hoặc model nội bộ |
| Mock sâu hàng chục class SDK | Test giòn khi SDK đổi | Mock port, test adapter riêng |
| Mọi test đều gọi cloud thật | Chậm, tốn quota, flaky | Tách unit/component và integration |
| Fake cho phép hành vi production cấm | Test xanh sai lệch | Viết contract tests |
| Gộp not-found và 403/503 | Che khuất lỗi quyền/hạ tầng | Phân loại và ánh xạ exception rõ |
| Dùng service account Owner cho integration test | Blast radius lớn | IAM least privilege và sandbox project |
| Dùng chung resource name giữa các build | Test ảnh hưởng lẫn nhau | Prefix duy nhất và cleanup |
| Test retry bằng sleep dài | Chậm và không ổn định | Inject clock/scheduler, kiểm soát thời gian |
| Ghi key hoặc token vào log để debug | Lộ credential | Log request ID, operation, status và trace ID |
| Tin emulator chứng minh IAM production | Bỏ sót lỗi auth/policy | Kiểm tra IAM trên GCP thật |
| Mở rộng interface cho mọi API SDK | Abstraction phình to, khó bảo trì | Thiết kế port theo use case |

## 19. Bài tập thực hành

Một ứng dụng Spring Boot lưu ảnh sản phẩm vào Cloud Storage và phát sự kiện `ProductImageUploaded` lên Pub/Sub. Ứng dụng hiện gọi `Storage` và `Publisher` ngay trong controller.

Yêu cầu:

1. Vẽ sơ đồ dependency sau khi tách thành controller, application service, `ImageStore` và `DomainEventPublisher`.
2. Thiết kế port với phương thức theo nghiệp vụ, không trả về SDK type.
3. Tạo adapter GCS và Pub/Sub riêng, inject qua Spring configuration.
4. Viết unit test xác nhận ảnh trống bị từ chối và không có event nào được publish.
5. Viết fake lưu ảnh bằng map và recording publisher; test ảnh hợp lệ được lưu trước khi event được phát.
6. Viết adapter test kiểm tra object path, metadata, Pub/Sub topic và serialization.
7. Chạy integration test với Pub/Sub emulator và project Cloud Storage thử nghiệm được cô lập.
8. Mô phỏng tình huống đã lưu ảnh nhưng publish thất bại; đề xuất outbox, idempotency hoặc cơ chế bù phù hợp.
9. Thêm cleanup và giới hạn quyền IAM cho integration test.
10. Xác định điều kiện nào đủ để cho phép merge và điều kiện nào chỉ kiểm tra được ở staging.

**Kết quả mong đợi:** có thể chạy toàn bộ unit/component tests mà không có Google Cloud credential, adapter có contract rõ, integration tests cô lập và pipeline chỉ cần quyền cloud ở đúng job cần thiết.

## 20. Câu hỏi tự kiểm tra

1. Tại sao việc tạo `StorageOptions` trong constructor của domain service làm unit test khó thực hiện?
2. Port và adapter khác nhau thế nào? Bên nào nên sở hữu interface?
3. Khi nào nên dùng Mockito mock và khi nào fake trong bộ nhớ có lợi hơn?
4. Vì sao contract test cần chạy cùng bộ kiểm tra trên fake và adapter?
5. Một fake trả `Optional.empty()` cho cả 404 và 403 sẽ gây lỗi gì?
6. Vì sao Pub/Sub emulator không đủ để xác nhận quyền IAM hoặc quota production?
7. Trong Spring Boot, làm sao thay GCS adapter bằng fake mà không yêu cầu ADC?
8. Việc dùng precondition create-only trên Cloud Storage ảnh hưởng contract và fake ra sao?
9. Vì sao retry một thao tác tạo tài nguyên không được xử lý như retry một thao tác đọc?
10. Test nào nên chạy trong pull request và test nào nên dùng sandbox project?
11. Làm sao để tránh chi phí hoặc dữ liệu rác sau cloud integration test?
12. Vì sao không nên kiểm tra từng lời gọi SDK nội bộ của Java library trong mọi unit test nghiệp vụ?

## Tài liệu tham khảo

- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Storage Java client reference](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Cloud Storage preconditions](https://cloud.google.com/storage/docs/request-preconditions)
- [Pub/Sub emulator](https://cloud.google.com/pubsub/docs/emulator)
- [Firestore emulator](https://cloud.google.com/firestore/native/docs/emulator)
- [Bigtable emulator](https://cloud.google.com/bigtable/docs/emulator)
- [Cloud Build overview](https://cloud.google.com/build/docs/overview)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Spring Framework testing](https://docs.spring.io/spring-framework/reference/testing.html)
- [JUnit 5 user guide](https://junit.org/junit5/docs/current/user-guide/)
- [Mockito](https://site.mockito.org/)
- [Testcontainers for Java](https://java.testcontainers.org/)

