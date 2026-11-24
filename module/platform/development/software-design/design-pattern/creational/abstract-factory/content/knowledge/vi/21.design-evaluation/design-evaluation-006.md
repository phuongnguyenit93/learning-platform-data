# Tổng hợp quyết định thiết kế, chi phí mở rộng và hướng bảo trì phù hợp

Khi học **Abstract Factory**, việc viết được interface factory và các concrete factory mới chỉ là bước đầu. Quyết định quan trọng hơn là **có nên áp dụng mẫu này trong hệ thống đang thiết kế không**, cần đặt ranh giới họ sản phẩm ở đâu, chi phí mở rộng theo thời gian ra sao và đội phát triển sẽ bảo trì các hợp đồng tương thích như thế nào.

Abstract Factory có ích khi client cần tạo **nhiều loại sản phẩm liên quan** mà các biến thể của chúng phải được lựa chọn **đồng bộ theo cùng một họ**. Mẫu thiết kế giúp tập trung việc chọn họ, nhưng cũng làm tăng số abstraction, concrete factory, cách cấu hình và bài kiểm thử cần quản lý.

Bài **Đánh giá thiết kế** này tổng hợp một cách ra quyết định thực tế: phân tích yêu cầu, lập ma trận sản phẩm, đánh giá hai chiều mở rộng, lựa chọn mức trừu tượng phù hợp, thiết kế vòng đời, xây dựng chiến lược kiểm thử và lên kế hoạch bảo trì khi các họ sản phẩm thay đổi.

## 1. Đừng bắt đầu từ tên mẫu thiết kế

Trước khi quyết định dùng Abstract Factory, hãy trả lời các câu hỏi về **nhu cầu của hệ thống**:

1. Client cần **những loại đối tượng nào** để hoàn thành một tác vụ? Chúng có những interface độc lập nào?
2. Những loại đối tượng ấy có **phải thay đổi cùng nhau** khi chọn một biến thể, nhà cung cấp, nền tảng hoặc giao thức không?
3. Nếu vô tình lấy sản phẩm từ hai họ khác nhau, chương trình sẽ lỗi kiểu dữ liệu, sai ngữ nghĩa, sai cấu hình hay vẫn hoạt động bình thường?
4. Trong tương lai, hệ thống dễ **thêm họ mới** hay **thêm loại sản phẩm mới** hơn?
5. Có cần cô lập logic client khỏi lớp cụ thể để kiểm thử, thay thế hoặc cấu hình theo môi trường/tenant không?
6. Phạm vi chọn factory là một ứng dụng, một màn hình, một request, một giao dịch hay một phiên làm việc?

Nếu chỉ có một interface với nhiều implementation thay thế, **Simple Factory**, Factory Method hoặc dependency injection có thể đủ. Nếu nhiều sản phẩm không cần chia sẻ một trục biến thể, mỗi dependency có thể được quản lý độc lập. **Abstract Factory đáng cân nhắc nhất khi có yêu cầu tạo cả một bộ sản phẩm tương thích.**

### Ví dụ xuyên suốt: xuất báo cáo lên hai dịch vụ lưu trữ

Một ứng dụng xuất báo cáo cần:

- `FileUploader`: tải nội dung báo cáo lên một dịch vụ.
- `ShareLinkGenerator`: tạo đường dẫn truy cập tới file đã tải lên.

Ứng dụng hỗ trợ **Cloud A** và **Cloud B**. Mã định danh file do Cloud A cấp không thể được Cloud B dùng để tạo đường dẫn. Đây là ràng buộc **tương thích ngữ nghĩa**: dù cả hai sản phẩm giao tiếp qua những interface Java hợp lệ, chúng phải cùng nhà cung cấp, đúng tài khoản và đúng môi trường.

Ma trận sản phẩm:

| Loại sản phẩm / Họ | Cloud A | Cloud B |
| --- | --- | --- |
| `FileUploader` | `CloudAUploader` | `CloudBUploader` |
| `ShareLinkGenerator` | `CloudALinkGenerator` | `CloudBLinkGenerator` |
| Quy ước chung | Mã file và tài khoản của A | Mã file và tài khoản của B |

Từ ma trận có thể xác định một `StorageFactory` gồm `createUploader()` và `createLinkGenerator()`. Client nhận **một** factory cho luồng xuất báo cáo, rồi tạo cả hai sản phẩm từ factory ấy.

## 2. Đánh giá lợi ích và đánh đổi

| Tiêu chí | Lợi ích khi dùng Abstract Factory | Chi phí/rủi ro phải chấp nhận |
| --- | --- | --- |
| **Tương thích họ sản phẩm** | Cùng một concrete factory cung cấp bộ sản phẩm được thiết kế để cộng tác | Concrete factory vẫn có thể triển khai sai; phải có hợp đồng và kiểm thử |
| **Độc lập implementation** | Client phụ thuộc các interface; đổi họ bằng cách thay factory | Thêm lớp/interface và bước cấu hình dependency |
| **Thêm họ mới** | Có thể bổ sung một concrete factory mà không sửa logic nghiệp vụ của client | Phải triển khai **đủ mọi loại sản phẩm** và đăng ký cách chọn họ |
| **Thêm loại sản phẩm** | Hợp đồng chung biểu diễn rõ nhu cầu của client | Thường phải sửa abstract factory và **tất cả** concrete factory |
| **Kiểm thử** | Inject factory giả lập hoặc chạy contract suite trên mọi họ | Ma trận kiểm thử tăng theo số họ và tương tác giữa sản phẩm |
| **Bảo trì** | Tách quy trình nghiệp vụ khỏi cách tạo adapter | Nếu ranh giới họ sai, factory dễ phình thành nơi chứa mọi dependency |
| **Vòng đời** | Một factory có thể giữ cấu hình hoặc ngữ cảnh chung | Phải quản lý ownership, thread safety và tài nguyên đúng phạm vi |

Một quyết định tốt không phải là “dùng mẫu mạnh nhất”, mà là **lựa chọn giải quyết vấn đề thực tế với chi phí có thể duy trì**. Khi chỉ có một vai trò sản phẩm hoặc không có ràng buộc họ, tăng trừu tượng có thể làm mã khó đọc hơn mà không tạo ra lợi ích rõ ràng.

## 3. Hai chiều mở rộng: thêm họ và thêm loại sản phẩm

Trong Abstract Factory, có hai trục thay đổi khác nhau:

- **Thêm họ (*family*)**: Ví dụ thêm Cloud C, vẫn cần hai loại sản phẩm `FileUploader` và `ShareLinkGenerator`.
- **Thêm loại sản phẩm (*product type*)**: Ví dụ bổ sung `FileDeleter` để xóa file, yêu cầu cả Cloud A và Cloud B đều cung cấp cách triển khai.

Giả sử có **F họ** và **P loại sản phẩm**. Nếu mỗi cặp *(họ, loại)* cần một implementation riêng, ma trận có tối đa **F × P ô triển khai**. Đây là mô hình ước lượng để trao đổi phạm vi công việc, **không phải số lớp bắt buộc**: một lớp có thể dùng chung cho nhiều ô nếu hợp đồng và cấu hình cho phép, hoặc một ô cần nhiều lớp hỗ trợ.

| Thay đổi | Số ô sản phẩm cần xem xét bổ sung | Tác động thường gặp |
| --- | ---: | --- |
| Thêm một họ mới | **P** ô | Concrete factory mới, cấu hình chọn họ, kiểm thử toàn bộ loại sản phẩm |
| Thêm một loại sản phẩm chung | **F** ô | Phương thức mới trong factory, cập nhật mọi concrete factory, kiểm thử và client liên quan |
| Thêm một họ và một loại | **F + P + 1** ô so với ma trận cũ | Cả hai chiều thay đổi và các trường hợp tích hợp mới |

Ví dụ ban đầu **2 họ × 2 loại = 4 ô**. Thêm Cloud C làm tăng lên **3 × 2 = 6 ô**; thêm `FileDeleter` khi có ba họ làm tăng lên **3 × 3 = 9 ô**.

**Lưu ý:** Không nên dùng con số ô làm thước đo duy nhất cho công sức thực hiện. Mỗi ô còn liên quan đến cấu hình, bộ kiểm thử hợp đồng, đặc tính API, quản lý lỗi, tài liệu và triển khai môi trường. Một adapter tưởng đơn giản có thể tốn nhiều công nếu nhà cung cấp có giao thức phức tạp.

### Chi phí thay đổi interface

Nếu sửa:

```java
interface StorageFactory {
    FileUploader createUploader();
    ShareLinkGenerator createLinkGenerator();
}
```

thành:

```java
interface StorageFactory {
    FileUploader createUploader();
    ShareLinkGenerator createLinkGenerator();
    FileDeleter createDeleter();
}
```

thì mọi concrete factory trước đó phải đáp ứng phương thức mới. Với các lớp triển khai interface, **thêm abstract method là thay đổi hợp đồng ở mức mã nguồn** và có thể làm những implementation cũ không còn biên dịch khi build lại.

Trong Java có thể dùng `default method` để tránh buộc sửa ngay mọi lớp trong một số tình huống, nhưng nếu phương thức mới mặc định ném `UnsupportedOperationException` trong khi client giả định mọi họ đều hỗ trợ xóa file thì **hợp đồng ngữ nghĩa vẫn bị phá vỡ**.

Nếu tính năng xóa chỉ áp dụng cho một số nhà cung cấp hoặc một luồng độc lập, hãy cân nhắc một capability riêng hay factory có phạm vi nhỏ hơn. **Không đưa sản phẩm vào abstract factory chung chỉ vì nó thuộc cùng lĩnh vực tên gọi.**

## 4. Ví dụ Java: factory chịu trách nhiệm về họ, service điều phối nghiệp vụ

Ví dụ dưới đây là chương trình **tự chứa**. Nó minh họa cách thiết kế không phụ thuộc vào nhà cung cấp trong lớp điều phối `ReportExportService`. Các adapter chỉ mô phỏng việc tải file và tạo link trong bộ nhớ; chúng **không truy cập dịch vụ cloud thật**.

```java
import java.util.Objects;

public class DesignEvaluationDemo {
    enum Provider { CLOUD_A, CLOUD_B }

    // Chứng từ giữ ngữ cảnh của nơi đã tải file.
    static final class UploadedFile {
        final Provider provider;
        final String account;
        final String fileId;

        UploadedFile(Provider provider, String account, String fileId) {
            this.provider = Objects.requireNonNull(provider);
            this.account = Objects.requireNonNull(account);
            this.fileId = Objects.requireNonNull(fileId);
        }
    }

    // Hai loại sản phẩm phải thuộc cùng một họ.
    interface FileUploader {
        UploadedFile upload(String reportId, String content);
    }

    interface ShareLinkGenerator {
        String createLink(UploadedFile file);
    }

    // Abstract Factory: tạo hai loại sản phẩm cùng provider và account.
    interface StorageFactory {
        FileUploader createUploader();
        ShareLinkGenerator createLinkGenerator();
    }

    static final class CloudAUploader implements FileUploader {
        private final String account;

        CloudAUploader(String account) {
            this.account = account;
        }

        public UploadedFile upload(String reportId, String content) {
            Objects.requireNonNull(content);
            System.out.println("Cloud A: tải " + reportId);
            return new UploadedFile(
                    Provider.CLOUD_A, account, "A-" + reportId);
        }
    }

    static final class CloudALinkGenerator implements ShareLinkGenerator {
        private final String account;

        CloudALinkGenerator(String account) {
            this.account = account;
        }

        public String createLink(UploadedFile file) {
            requireContext(file, Provider.CLOUD_A, account);
            return "cloud-a://" + account + "/" + file.fileId;
        }
    }

    static final class CloudBUploader implements FileUploader {
        private final String account;

        CloudBUploader(String account) {
            this.account = account;
        }

        public UploadedFile upload(String reportId, String content) {
            Objects.requireNonNull(content);
            System.out.println("Cloud B: tải " + reportId);
            return new UploadedFile(
                    Provider.CLOUD_B, account, "B-" + reportId);
        }
    }

    static final class CloudBLinkGenerator implements ShareLinkGenerator {
        private final String account;

        CloudBLinkGenerator(String account) {
            this.account = account;
        }

        public String createLink(UploadedFile file) {
            requireContext(file, Provider.CLOUD_B, account);
            return "cloud-b://" + account + "/" + file.fileId;
        }
    }

    private static void requireContext(
            UploadedFile file, Provider provider, String account) {
        if (file == null || file.provider != provider
                || !account.equals(file.account)) {
            throw new IllegalArgumentException(
                    "Sản phẩm không cùng provider hoặc account");
        }
    }

    static final class CloudAFactory implements StorageFactory {
        private final String account;

        CloudAFactory(String account) {
            this.account = Objects.requireNonNull(account);
        }

        public FileUploader createUploader() {
            return new CloudAUploader(account);
        }

        public ShareLinkGenerator createLinkGenerator() {
            return new CloudALinkGenerator(account);
        }
    }

    static final class CloudBFactory implements StorageFactory {
        private final String account;

        CloudBFactory(String account) {
            this.account = Objects.requireNonNull(account);
        }

        public FileUploader createUploader() {
            return new CloudBUploader(account);
        }

        public ShareLinkGenerator createLinkGenerator() {
            return new CloudBLinkGenerator(account);
        }
    }

    // Điều phối nghiệp vụ dùng abstraction, không biết các concrete class.
    static final class ReportExportService {
        private final StorageFactory factory;

        ReportExportService(StorageFactory factory) {
            this.factory = Objects.requireNonNull(factory);
        }

        String exportAndShare(String reportId, String content) {
            if (reportId == null || reportId.trim().isEmpty()) {
                throw new IllegalArgumentException("Thiếu mã báo cáo");
            }
            if (content == null || content.isEmpty()) {
                throw new IllegalArgumentException("Báo cáo rỗng");
            }

            FileUploader uploader = factory.createUploader();
            ShareLinkGenerator links = factory.createLinkGenerator();
            UploadedFile file = uploader.upload(reportId, content);
            return links.createLink(file);
        }
    }

    // Composition root chọn một họ và ngữ cảnh trước khi chạy nghiệp vụ.
    static StorageFactory selectFactory(
            Provider provider, String account) {
        if (provider == Provider.CLOUD_A) {
            return new CloudAFactory(account);
        }
        if (provider == Provider.CLOUD_B) {
            return new CloudBFactory(account);
        }
        throw new IllegalArgumentException("Provider không được hỗ trợ");
    }

    public static void main(String[] args) {
        Provider selected = args.length > 0
                && "B".equalsIgnoreCase(args[0])
            ? Provider.CLOUD_B : Provider.CLOUD_A;

        StorageFactory factory = selectFactory(selected, "demo-account");
        ReportExportService service = new ReportExportService(factory);
        String link = service.exportAndShare("REPORT-001", "Nội dung báo cáo");
        System.out.println("Đường dẫn: " + link);
    }
}
```

Lưu thành `DesignEvaluationDemo.java`, biên dịch và chạy với JDK:

```bash
javac -encoding UTF-8 DesignEvaluationDemo.java
java DesignEvaluationDemo
java DesignEvaluationDemo B
```

Đầu ra dự kiến cho lần chạy thứ nhất:

```text
Cloud A: tải REPORT-001
Đường dẫn: cloud-a://demo-account/A-REPORT-001
```

Lần thứ hai dùng Cloud B:

```text
Cloud B: tải REPORT-001
Đường dẫn: cloud-b://demo-account/B-REPORT-001
```

`cloud-a://` và `cloud-b://` chỉ là **chuỗi mô phỏng**, không phải URL chia sẻ hợp lệ của nhà cung cấp thật. Ví dụ có chủ đích tập trung vào ranh giới lớp, không mô phỏng xác thực, upload mạng hoặc phân quyền truy cập.

### Đánh giá thiết kế của ví dụ

- **Đúng vấn đề:** việc tạo link phải dựa trên file do bộ upload **cùng provider và account** tạo ra.
- **Ranh giới rõ:** factory cung cấp bộ adapter và ngữ cảnh chung; `ReportExportService` quyết định xác thực đầu vào và trình tự upload → tạo link.
- **Có điểm thay thế:** có thể thay `CloudAFactory` bằng `CloudBFactory` ở nơi lắp ghép mà không đổi code service.
- **Có ràng buộc ngữ nghĩa:** `requireContext(...)` phát hiện tình huống trộn provider hoặc account. Interface chung tự nó không ngăn được lỗi này.
- **Vẫn có chi phí:** thêm Cloud C cần adapter, factory mới, thay đổi điểm chọn và chạy lại bộ kiểm thử hợp đồng.

Điểm hạn chế của ví dụ: mỗi lần chạy chỉ xử lý một báo cáo và không cần lưu trạng thái. Trong hệ thống thật, nếu một báo cáo đã nằm trên Cloud A nhưng hôm sau cấu hình mặc định chuyển sang Cloud B, bước tạo lại link **phải dựa vào provider/account đã lưu trong chứng từ**, không được tùy tiện dùng factory mặc định mới. Đồng thời cần kiểm soát idempotency, quyền truy cập, retry và vòng đời tài nguyên theo hợp đồng dịch vụ thực tế.

## 5. Lựa chọn phạm vi factory: một “họ” là gì?

Một rủi ro phổ biến khi áp dụng Abstract Factory là gom mọi dependency có liên quan về mặt tên gọi vào cùng một interface. **Họ sản phẩm phải được xác định bằng ràng buộc tương thích hoặc nhu cầu thay thế đồng bộ**, thay vì chỉ cùng thư mục, cùng module hoặc cùng công ty cung cấp.

Trong bài toán Cloud:

| Dependency | Có nên đặt trong `StorageFactory`? | Lý do |
| --- | --- | --- |
| `FileUploader` | Có | Tạo file và trả về định danh theo cloud đã chọn |
| `ShareLinkGenerator` | Có | Phải hiểu đúng định danh và ngữ cảnh từ uploader |
| `ReportTemplateEngine` | Thường không | Việc dựng nội dung báo cáo có thể độc lập với cloud |
| `AuditLogger` | Thường không | Ghi nhật ký có thể không phụ thuộc nhà cung cấp |
| `FileDeleter` | Tùy hợp đồng | Nên chung họ nếu xóa file cùng hệ lưu trữ là trách nhiệm bắt buộc của mọi cloud |
| `MetricReporter` | Thường không | Metric có thể là dịch vụ hạ tầng dùng chung |

Nếu `ReportTemplateEngine` có cả phiên bản cho Cloud A và Cloud B **chỉ do trùng tên**, việc đưa nó vào factory sẽ khiến mỗi concrete factory phải tạo thêm một sản phẩm không thực sự cần thay đổi đồng bộ.

### Khi nào nên tách thành các factory nhỏ?

Cân nhắc tách khi:

- Các nhóm sản phẩm có **trục biến thể khác nhau**, chẳng hạn renderer theo Light/Dark nhưng storage theo Cloud A/B.
- Một số loại sản phẩm chỉ được một phần họ hỗ trợ; interface chung bắt đầu chứa nhiều phương thức ném `UnsupportedOperationException`.
- Các client khác nhau thường chỉ cần một nhóm nhỏ sản phẩm, trong khi factory trở thành “bảng dịch vụ” quá lớn.
- Vòng đời và ngữ cảnh của sản phẩm khác nhau đáng kể, ví dụ connection theo giao dịch và client cấu hình bất biến dùng chung ứng dụng.

Tách nhỏ phải dựa trên **ranh giới nghiệp vụ và tính tương thích thực tế**, không phải áp dụng máy móc một interface cho mỗi phương thức.

## 6. So sánh với các lựa chọn đơn giản hơn

| Bối cảnh | Hướng lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Một loại sản phẩm có nhiều implementation, như `Parser` | Simple Factory, Factory Method hoặc DI | Chưa có bộ nhiều loại sản phẩm cùng họ |
| Chỉ cần một instance được cấu hình sẵn trong cả ứng dụng | Inject trực tiếp abstraction | Không có nhu cầu tạo thêm ở client |
| Hai hoặc nhiều loại sản phẩm phải cùng giao thức, nhà cung cấp hoặc chủ đề | Abstract Factory | Giữ lựa chọn biến thể nhất quán |
| Một họ sản phẩm cần tạo từ các mẫu đã cấu hình phức tạp | Abstract Factory kết hợp Prototype | Factory quản lý họ; Prototype quản lý cơ chế sao chép |
| Sản phẩm có cách lắp ghép cấu hình phức tạp nhưng không có nhiều họ | Builder hoặc một factory phù hợp | Vấn đề chính nằm ở quá trình xây dựng một sản phẩm |
| Chỉ một nơi sử dụng, biến thể chưa chắc sẽ xuất hiện | Có thể tạo trực tiếp qua constructor | Trừu tượng hóa sớm làm tăng chi phí mà chưa có lợi ích rõ |

Các lựa chọn không nhất thiết loại trừ nhau. Ví dụ `selectFactory(...)` trong mã Java sử dụng điều kiện để chọn **concrete factory**, trong khi Abstract Factory quản lý **các sản phẩm của họ đã chọn**. Có thể dùng dependency injection container hoặc registry thay điểm chọn khi hệ thống cần cấu hình động, nhưng không nên coi công cụ DI là một sự thay thế tự động cho **hợp đồng tương thích giữa các sản phẩm**.

## 7. Đánh giá vòng đời, trạng thái và tài nguyên

Một thiết kế hợp lý về cấu trúc lớp vẫn có thể gây lỗi nếu factory và sản phẩm giữ tài nguyên nhưng không xác định **ai sở hữu, ai đóng và đóng khi nào**.

### Những câu hỏi cần giải đáp

1. Factory chỉ giữ cấu hình bất biến hay giữ HTTP client, connection pool, thread pool hoặc tài nguyên cần đóng?
2. Sản phẩm được tạo mới mỗi lần gọi hay dùng chung? Nó có thread-safe không?
3. Nếu một request tạo uploader và link generator, hai đối tượng có cần cùng phiên, tenant, account hay credential không?
4. Factory có an toàn để dùng như singleton không, hay phải tạo theo request hoặc phiên làm việc?
5. Nếu một bước khởi tạo sản phẩm thất bại sau khi đã mở tài nguyên, **ai dọn dẹp phần đã cấp phát**?

Nếu sản phẩm nắm giữ tài nguyên như stream hoặc connection, có thể cho sản phẩm triển khai `AutoCloseable` và để bên **sở hữu sản phẩm** sử dụng `try-with-resources`. Nếu factory sở hữu pool dùng chung, thành phần sở hữu factory phải đóng nó khi phạm vi sử dụng kết thúc. Không nên để mỗi request tự đóng pool dùng chung.

**Cùng class factory chưa chắc cùng ngữ cảnh.** Hai `CloudAFactory` được cấu hình cho account khác nhau có thể tạo ra hai sản phẩm không thể cộng tác, dù cả hai đều là sản phẩm “Cloud A”. Thiết kế phải thể hiện đúng ranh giới account, tenant, môi trường và phiên bản, không chỉ dựa trên tên concrete class.

## 8. Kiểm thử hợp đồng: điều kiện bắt buộc để thay họ an toàn

Lợi ích thay factory chỉ đáng tin khi **mỗi concrete factory tuân thủ cùng một bộ hợp đồng**. Hãy tách hai lớp kiểm thử:

1. **Contract tests cho họ sản phẩm:** xác minh mọi factory tạo đúng các loại sản phẩm, đồng nhất cấu hình cần thiết và hoàn thành các tương tác giữa sản phẩm.
2. **Tests cho luồng nghiệp vụ:** xác minh service quyết định đúng thứ tự và xử lý lỗi, thường dùng test doubles cho dependency không phải đối tượng được tích hợp trong phép thử.

Ví dụ về **contract test đơn giản** sử dụng các class trong `DesignEvaluationDemo`:

```java
// Có thể đặt phương thức này bên trong DesignEvaluationDemo.
static void verifyFactory(StorageFactory factory) {
    FileUploader uploader = factory.createUploader();
    ShareLinkGenerator generator = factory.createLinkGenerator();

    UploadedFile uploaded = uploader.upload("CHECK-001", "nội dung");
    String link = generator.createLink(uploaded);

    if (link == null || link.isEmpty()) {
        throw new AssertionError("Factory tạo cặp sản phẩm không hoạt động");
    }
}

static void verifyAllFactories() {
    verifyFactory(new CloudAFactory("account-test"));
    verifyFactory(new CloudBFactory("account-test"));
}
```

Test trên kiểm tra được sự cộng tác trong **mô hình giả lập** của ví dụ; trong ứng dụng thật, cần bổ sung oracle kiểm tra link thực sự trỏ tới file đã upload, đúng quyền truy cập, đúng account và có thể truy cập theo chính sách. Không nên dùng cùng logic sai trong cả hai sản phẩm rồi kết luận “round-trip thành công là đủ”: cần dữ liệu chuẩn và nguồn kỳ vọng độc lập.

### Ma trận kiểm thử bảo trì

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| Upload A → tạo link bằng A cùng account | Thành công | Cặp sản phẩm đúng họ |
| Upload B → tạo link bằng B cùng account | Thành công | Cặp sản phẩm đúng họ |
| Upload A → tạo link bằng B | Từ chối theo hợp đồng ví dụ | Phát hiện trộn họ |
| Upload A/account X → tạo link A/account Y | Từ chối | Phát hiện trộn ngữ cảnh |
| Upload thất bại | Service không báo xuất báo cáo thành công | Điều phối lỗi |
| Upload thành công nhưng tạo link thất bại | Có trạng thái phục hồi hoặc đối soát | Không mất dấu tài nguyên đã tạo |
| Thêm Cloud C | Chạy lại contract suite trên toàn bộ loại sản phẩm | Hạn chế hồi quy khi mở rộng |

Trong một hệ thống có yêu cầu tương thích chéo hoặc hỗ trợ chia sẻ giữa account, ma trận phải được điều chỉnh **theo quy định nghiệp vụ đã công bố**. Mẫu Abstract Factory không tự quy định rằng mọi tổ hợp khác họ luôn bị cấm.

## 9. Chiến lược bảo trì khi các yêu cầu thay đổi

### Tình huống A: Thêm một concrete family

Giả sử bổ sung Cloud C. Quy trình hợp lý:

1. Xác định hợp đồng chung mà Cloud C phải đáp ứng: upload, tạo link, định danh, account, quyền truy cập.
2. Viết `CloudCUploader` và `CloudCLinkGenerator` cùng ngữ cảnh.
3. Tạo `CloudCFactory` triển khai đầy đủ `StorageFactory`.
4. Bổ sung cách chọn/đăng ký Cloud C tại điểm lắp ghép, kèm cấu hình và kiểm tra tính hợp lệ.
5. Chạy contract suite chung, các bài test đặc thù Cloud C và kiểm thử luồng xuất báo cáo.
6. Cập nhật tài liệu giới hạn của provider, vận hành, cấu hình và quy trình đối soát lỗi.

Client sử dụng abstraction có thể giữ nguyên, **nhưng** điểm đăng ký, cấu hình và môi trường vẫn cần được quản lý. Không nên khẳng định chỉ việc tạo một concrete factory mới là toàn hệ thống tự nhận ra provider mới.

### Tình huống B: Thêm loại sản phẩm chung

Giả sử tất cả các cloud đều phải hỗ trợ `FileDeleter` để dọn dẹp file sau khi báo cáo hết hạn. Trước khi thêm `createDeleter()`, cần kiểm tra:

- Mỗi provider **thực sự** có khả năng xóa tương đương theo hợp đồng không?
- Xóa file có cùng ràng buộc provider/account với upload và tạo link không?
- Nếu một nhà cung cấp xóa bất đồng bộ, interface chung có diễn đạt rõ trạng thái `PENDING`, `DONE`, `FAILED` không?
- Những client nào cần sản phẩm xóa, và có thể mở rộng hợp đồng mà không làm client cũ hiểu sai không?

Nếu câu trả lời phù hợp, mở rộng Abstract Factory và cập nhật từng concrete factory. Nếu không, cân nhắc một **capability interface riêng**, một tác vụ bảo trì độc lập hoặc thiết kế lại ranh giới factory thay vì đưa vào phương thức mặc định ném lỗi.

### Tình huống C: Thay đổi luồng nghiệp vụ

Nếu ứng dụng cần kiểm tra quyền chia sẻ, lưu metadata hoặc gửi thông báo sau khi tạo link, thay đổi này thường thuộc **ReportExportService** hay các thành phần điều phối liên quan. Chỉ cần sửa factory nếu có một yêu cầu mới về **loại sản phẩm hoặc cách cấu hình sản phẩm**.

Điều này giúp tránh việc concrete factory của Cloud A, B và C chứa ba bản sao quy trình nghiệp vụ khác nhau.

### Tình huống D: Chuyển đổi từ code cũ

Một lộ trình chuyển đổi ít rủi ro:

1. **Ghi nhận hành vi hiện tại:** tên provider, các đối tượng liên quan, tài nguyên và quy tắc tương thích của từng cặp.
2. **Tạo interface sản phẩm:** bao quanh các adapter hiện có, giữ nguyên hành vi đã được kiểm thử.
3. **Tạo Abstract Factory:** mỗi concrete factory chỉ chịu trách nhiệm cấp các adapter thuộc cùng họ.
4. **Dời điểm chọn biến thể:** gom những nhánh `if/switch` ở client về điểm cấu hình hoặc composition root.
5. **Inject factory vào service:** để logic nghiệp vụ chỉ làm việc qua các abstraction và giữ nguyên trình tự xử lý cần thiết.
6. **Chạy thử từng họ và chuyển dần:** bổ sung contract tests; khi được phép, chuyển từng luồng sang cơ chế mới, quan sát lỗi rồi loại bỏ nhánh khởi tạo cũ.

Không nhất thiết refactor tất cả client trong một lần. Với hệ thống có nhiều provider hoặc môi trường, có thể chuyển đổi theo từng luồng, miễn là tránh trộn sản phẩm từ hai cách cấu hình trong cùng một giao dịch.

## 10. Các dấu hiệu cần xem lại quyết định thiết kế

| Dấu hiệu trong code hoặc vận hành | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Client thường xuyên ép kiểu về `CloudAUploader` | Interface sản phẩm thiếu hợp đồng cần thiết hoặc dùng sai abstraction | Xem lại khả năng chung, không đưa điều kiện provider tràn vào client |
| Concrete factory có hàng chục phương thức tạo ít liên quan | Ranh giới họ sản phẩm quá rộng | Phân nhóm lại theo biến thể và tương tác thật |
| Nhiều phương thức trả `null` hoặc ném `UnsupportedOperationException` | Không phải họ nào cũng hỗ trợ cùng capability | Xem lại hợp đồng chung, tách capability hoặc factory |
| Thêm một loại sản phẩm làm sửa mọi factory và nhiều client | Chi phí mở rộng theo trục loại sản phẩm | Cân nhắc tính bắt buộc của loại mới và tách interface phù hợp |
| Một factory dùng chung bị thay cấu hình khi đang có request | Phạm vi sống/cấu hình sai | Dùng factory bất biến hoặc scope theo tenant/request |
| Bài test chỉ kiểm tra `instanceof` | Chưa kiểm tra tương thích ngữ nghĩa | Bổ sung integration/contract tests trên cặp sản phẩm |
| Adapter cùng provider nhưng hoạt động trên account khác | Factory không bảo toàn ngữ cảnh | Ràng buộc account và kiểm tra trên kết quả |
| Logic upload → tạo link nằm trong từng concrete factory | Trộn logic tạo sản phẩm với điều phối | Chuyển workflow về service |
| Có nhiều lớp factory nhưng chỉ một sản phẩm đơn giản | Có thể đang trừu tượng hóa quá sớm | Đánh giá Simple Factory hoặc inject trực tiếp |

**Không phải mọi dấu hiệu đều buộc phải refactor ngay.** Hãy dựa trên lỗi thực tế, mức thay đổi dự kiến, chi phí kiểm thử và mức ảnh hưởng tới client để chọn thứ tự xử lý.

## 11. Rubric đánh giá thiết kế trước khi triển khai

Có thể dùng bảng dưới đây như công cụ thảo luận trong buổi review. Chấm **0 = chưa đạt**, **1 = đạt một phần**, **2 = đạt rõ ràng** cho mỗi tiêu chí; điểm chỉ giúp nhóm nhìn thấy vấn đề, **không phải công thức tự động quyết định dùng pattern**.

| Tiêu chí | 0 điểm | 1 điểm | 2 điểm |
| --- | --- | --- | --- |
| **Sự cần thiết của họ** | Các sản phẩm độc lập | Có liên quan nhưng chưa có ràng buộc rõ | Cần được chọn cùng biến thể để cộng tác đúng |
| **Hợp đồng tương thích** | Chỉ có tên lớp/interface | Có mô tả nhưng thiếu trường hợp biên | Có bất biến ngữ nghĩa rõ, đo/kiểm thử được |
| **Mức ổn định của loại sản phẩm** | Thường xuyên thêm/xóa loại | Một số loại còn thay đổi | Các loại chung tương đối ổn định |
| **Nhu cầu thay thế họ** | Chỉ một biến thể, không có kế hoạch thay | Có nhu cầu dự kiến | Có nhiều họ đang dùng hoặc sẽ được hỗ trợ rõ ràng |
| **Ranh giới trách nhiệm** | Factory chứa nghiệp vụ | Còn vài nhánh tạo phân tán | Tạo sản phẩm và workflow được tách nhất quán |
| **Chiến lược kiểm thử** | Chỉ compile/kiểm tra kiểu | Có test từng implementation | Có contract/integration tests theo họ và ngữ cảnh |
| **Ownership/vòng đời** | Không xác định | Có tài liệu nhưng chưa kiểm tra | Có scope, cấu hình và cơ chế đóng/thu hồi rõ ràng |

Sau khi chấm, hãy thảo luận những hàng được **0 hoặc 1**: có cần làm rõ hợp đồng, chọn phạm vi factory nhỏ hơn, thêm test hay dùng giải pháp đơn giản hơn không? Một dự án có thể quyết định **chưa dùng Abstract Factory** dù điểm các tiêu chí kỹ thuật tốt, nếu chi phí cấu trúc không tương xứng với nhu cầu.

## 12. Một quyết định thiết kế mẫu có thể trình bày trong review

**Bối cảnh:** Báo cáo được lưu trên Cloud A hoặc Cloud B. Uploader và LinkGenerator phải dùng cùng provider và account; ứng dụng cần hỗ trợ thêm provider theo thời gian.

**Quyết định:** Dùng `StorageFactory` với hai phương thức tạo `FileUploader` và `ShareLinkGenerator`. Composition root chọn concrete factory theo cấu hình của tác vụ. `ReportExportService` điều phối kiểm tra đầu vào, upload và tạo link; chứng từ lưu provider/account cần thiết để xử lý lại về sau.

**Lợi ích mong đợi:** Client không phụ thuộc lớp adapter cụ thể; các sản phẩm được cấp qua một factory cùng ngữ cảnh; thêm Cloud C có thể giữ nguyên logic service nếu hợp đồng chung không đổi.

**Đánh đổi:** Tăng abstraction và mã lắp ghép; thêm một loại sản phẩm vào factory sẽ ảnh hưởng mọi concrete factory; phải kiểm tra các adapter không trộn provider/account và cùng tuân thủ quy tắc lỗi.

**Điều kiện chấp nhận:** Có contract tests cho ít nhất Cloud A và B; có bài test trộn họ/account; cấu hình factory được chọn rõ theo phạm vi; cách xử lý lỗi upload thành công nhưng tạo link thất bại được mô tả trong workflow.

**Khi xem xét lại:** Nếu về sau chỉ còn một provider, client không cần tạo nhiều loại sản phẩm hoặc các loại thay đổi độc lập, đánh giá việc thu gọn factory và loại bỏ các tầng trừu tượng không còn giá trị. Nếu xuất hiện các loại sản phẩm không được mọi provider hỗ trợ, xem lại ranh giới/capability thay vì thêm phương thức không thực hiện được.

## 13. Bài tập tự đánh giá

Một công ty triển khai công cụ thông báo với ba kênh: **Email**, **SMS** và **Push**. Mỗi kênh có một `MessageSender`. Đồng thời, một hệ thống phân tích chạy hai engine **Engine X** và **Engine Y**; mỗi engine cần một `QueryBuilder` và `ResultMapper` phải dùng chung dialect, quy tắc mapping và phiên bản schema.

Hãy đánh giá:

1. Trường hợp MessageSender nên ưu tiên Simple Factory/DI hay Abstract Factory? Tại sao?
2. Trường hợp QueryBuilder + ResultMapper có tạo thành họ sản phẩm không? Những ràng buộc ngữ nghĩa nào cần kiểm tra?
3. Nếu engine phân tích tăng từ 2 lên 4, nhưng vẫn chỉ có 2 loại sản phẩm, số ô ma trận thay đổi ra sao?
4. Nếu cần thêm `SchemaValidator` cho mọi engine, chi phí thay đổi nằm ở trục nào? Cần kiểm chứng gì trước khi thêm phương thức vào factory?
5. Nếu engine X và Y dùng chung một mapper thật sự độc lập với dialect, có nhất thiết tạo hai lớp mapper không?
6. Nếu query builder phụ thuộc connection đang mở, cần mô tả ownership và vòng đời như thế nào?

**Gợi ý:** Với một loại `MessageSender`, Simple Factory hoặc DI có thể đủ. Với `QueryBuilder` và `ResultMapper` cần chọn cùng engine/dialect, Abstract Factory đáng cân nhắc. Ma trận từ **2 × 2 = 4** lên **4 × 2 = 8 ô**; thêm một loại sản phẩm cho 4 engine tạo thành **4 × 3 = 12 ô**. Không phải mỗi ô bắt buộc là một class riêng nếu có triển khai dùng chung đúng hợp đồng. Cần kiểm tra schema, kiểu dữ liệu, đơn vị, quyền sở hữu connection và tính tương thích khi mapper đọc kết quả do builder tạo ra.

## Tổng kết

Đánh giá Abstract Factory cần nhìn đồng thời **ba yếu tố**: có thật sự tồn tại **họ sản phẩm phải cộng tác**, chi phí mở rộng theo **hai chiều họ và loại sản phẩm**, và khả năng duy trì **hợp đồng, vòng đời cùng kiểm thử** theo thời gian.

Hãy dùng Abstract Factory khi client cần đổi **cả một bộ sản phẩm tương thích** qua một interface ổn định. Đặt lựa chọn họ tại một điểm cấu hình, giữ workflow ở tầng điều phối, ghi rõ các bất biến ngữ nghĩa và chạy contract tests trên mỗi concrete factory. Khi hệ thống nhỏ hoặc chỉ có một loại sản phẩm độc lập, chọn giải pháp đơn giản hơn vẫn là một quyết định thiết kế hợp lý. Một mẫu thiết kế tốt là mẫu làm **thay đổi dự kiến dễ thực hiện hơn mà không chuyển gánh nặng sang các phần khác của hệ thống**.
