# Thiết kế fixture có thể nạp lại và tránh trùng ID

Một fixture có thể được nạp ở lần khởi động đầu, khi chạy lại kiểm thử hoặc sau một lần khởi tạo bị gián đoạn. Nếu mỗi lần nạp đều tạo những định danh logic mới, dữ liệu mẫu sẽ bị nhân bản. Nếu chỉ dùng lại ID rồi gọi `save`, ứng dụng lại có thể cập nhật ngoài ý muốn, gặp lỗi version hoặc ghi đè dữ liệu đã được người dùng sửa.

Trong chương **Khởi tạo dữ liệu** của **Spring Data Commons**, bài học này thiết kế fixture theo hợp đồng định danh và chính sách chạy lặp rõ ràng. Repository và CRUD là công cụ lưu dữ liệu; khả năng phát hiện entity mới, transaction, ràng buộc duy nhất, derived query và auditing vẫn phải được đối chiếu với module lưu trữ đang dùng.

## 1. Có thể nạp lại nghĩa là gì?

Cần định nghĩa kết quả mong muốn trước khi chọn cách ghi.

Với cùng một fixture D và trạng thái dữ liệu S, một cách diễn đạt tính idempotent là:

```text
apply(apply(S, D), D) = apply(S, D)
```

Đẳng thức phải được hiểu theo phạm vi trạng thái mà ứng dụng cam kết giữ. Ví dụ lần chạy sau không tạo thêm sản phẩm, không thay đổi thuộc tính nghiệp vụ đã đúng và không phát sinh lặp một tác dụng phụ bắt buộc phải duy nhất.

Nếu mỗi lần chạy đều đổi timestamp hoặc phát sự kiện ra bên ngoài, số bản ghi có thể không tăng nhưng toàn bộ tác động của thao tác vẫn chưa chắc idempotent.

Ba yêu cầu cần tách biệt:

| Yêu cầu | Ví dụ |
|---|---|
| Không trùng định danh vật lý | Không có hai bản ghi cùng primary key trong phạm vi của kho dữ liệu |
| Không trùng đối tượng nghiệp vụ | Không có hai sản phẩm cùng tenant và cùng mã sản phẩm |
| Nạp lại đúng chính sách | Dữ liệu có sẵn được giữ nguyên, kiểm tra hoặc cập nhật theo quy tắc đã chọn |

Một unique primary key không tự giải quyết hai yêu cầu còn lại nếu mỗi lần nạp lại dùng một ID mới cho cùng một sản phẩm.

## 2. Phân biệt ID persistence và khóa nghiệp vụ

Giả sử một sản phẩm có:

```text
id: 1042
 tenantId: tenant-demo
 code: BOOK-SPRING
 title: Spring Data cơ bản
```

`id` là định danh persistence. Cặp `(tenantId, code)` có thể là khóa nghiệp vụ ổn định mà fixture dùng để nhận ra cùng một sản phẩm qua nhiều lần nạp.

Nếu lần sau tạo bản ghi ID 1057 với cùng tenant/code, primary key vẫn khác nhau nhưng dữ liệu nghiệp vụ đã bị trùng.

Có hai chiến lược thường gặp:

| Chiến lược | Cách nhận diện cùng đối tượng |
|---|---|
| Fixture dùng ID gán trước | ID được xác định ổn định và module hỗ trợ cách lưu tương ứng |
| Persistence sinh ID | Fixture tra cứu bằng khóa nghiệp vụ ổn định rồi chỉ tạo khi cần |

Không bắt buộc chuyển mọi ID do database sinh thành ID gán trước để có khả năng nạp lại. Có thể để persistence sinh ID ở lần tạo đầu, miễn các lần sau nhận diện đúng đối tượng bằng một khóa ổn định khác.

Khóa nghiệp vụ cần phản ánh đúng phạm vi. `code` có thể duy nhất trong một tenant nhưng không duy nhất toàn hệ thống. Một số kho dữ liệu còn có phạm vi partition hoặc namespace riêng cần được tính đến.

## 3. Thiết kế định danh ổn định cho fixture

Một fixture không nên dùng dữ liệu biến đổi theo mỗi lần chạy để tạo định danh logic:

```text
UUID ngẫu nhiên mới cho cùng một mục mỗi lần nạp.
Timestamp hiện tại được ghép vào khóa của cùng một sản phẩm.
Số thứ tự phụ thuộc vị trí trong một danh sách thường xuyên bị sắp xếp lại.
```

Những lựa chọn này có thể phù hợp cho tạo đối tượng mới thật sự, nhưng không giúp nhận diện lại cùng một mục seed.

Một ID fixture dạng chuỗi có thể thể hiện namespace:

```text
seed:demo:category:BOOKS
seed:demo:category:COURSES
```

Đây là ví dụ quy ước, không phải cú pháp bắt buộc của Spring Data. Nếu module dùng ID kiểu UUID, số hoặc kiểu giá trị khác, cần chọn cách biểu diễn tương ứng.

Những quy tắc hữu ích:

- Định danh dựa trên khóa nguồn ổn định, không dựa trên tên hiển thị có thể được sửa.
- Namespace phân biệt phạm vi tenant/dataset khi cần.
- Cách ghép nhiều thành phần không được tạo chuỗi mơ hồ.
- Chuẩn hóa khóa trước khi kiểm tra trùng và trước khi truy vấn.
- Việc đổi mã nghiệp vụ được xem như một thay đổi định danh cần có kế hoạch chuyển đổi.

Không tự đưa version fixture vào ID nếu cùng một đối tượng phải được cập nhật qua các version. Đổi từ `v1:BOOKS` sang `v2:BOOKS` sẽ tạo hai định danh khác nhau, không phải cập nhật cùng một danh mục.

## 4. Chuẩn hóa khóa trước khi phát hiện trùng

Nếu hệ thống coi `book-spring`, `BOOK-SPRING` và chuỗi có khoảng trắng ngoài là cùng một mã, fixture cần áp dụng đúng quy tắc đó trước khi kiểm tra.

Ví dụ input của một đợt seed sản phẩm:

```java
import java.util.Locale;

record SeedProduct(String code, String title) {

    SeedProduct {
        if (code == null || title == null) {
            throw new IllegalArgumentException("Fixture thiếu code hoặc title");
        }

        code = code.strip().toUpperCase(Locale.ROOT);
        title = title.strip();

        if (!code.matches("[A-Z0-9][A-Z0-9_-]{0,63}")) {
            throw new IllegalArgumentException("Mã sản phẩm fixture không hợp lệ");
        }
        if (title.isBlank() || title.length() > 200) {
            throw new IllegalArgumentException("Tiêu đề fixture không hợp lệ");
        }
    }
}
```

Ví dụ dùng Java record và một quy tắc mã ASCII được ứng dụng lựa chọn. Giới hạn độ dài không phải mặc định của Spring Data.

Chuẩn hóa phải thống nhất với chính sách lưu trữ và ràng buộc duy nhất. Nếu database dùng collation khác hoặc ứng dụng coi hoa/thường là hai mã khác nhau, không sao chép quy tắc trên mà chưa xác định hợp đồng.

Không tự chuẩn hóa mạnh một khóa đã tồn tại từ trước nếu việc đó có thể làm hai đối tượng đang hợp lệ trở thành cùng khóa. Thay quy tắc định danh là một thay đổi dữ liệu cần được xử lý có chủ đích.

## 5. Kiểm tra cả tập fixture trước khi ghi

Một file hợp lệ về JSON/XML vẫn có thể chứa hai mục cùng khóa. Nhiều resource riêng cũng có thể định nghĩa trùng cùng một mục.

Có thể kiểm tra sau khi đã đọc và chuẩn hóa toàn bộ tập input cần nạp:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class FixtureValidation {

    static void requireUniqueCodes(List<SeedProduct> products) {
        Set<String> seen = new HashSet<>();

        for (SeedProduct product : products) {
            if (!seen.add(product.code())) {
                throw new IllegalArgumentException(
                        "Trùng mã trong fixture: " + product.code());
            }
        }
    }
}
```

Ví dụ áp dụng cho một đợt nạp thuộc **một tenant đã xác định**. Nếu input gồm nhiều tenant, khóa kiểm tra nên là một cấu trúc chứa cả tenant và code, thay vì chỉ `code`.

Cần kiểm tra trên tập kết hợp nếu nhiều resource cùng tham gia một đợt. Hai file tự không trùng bên trong vẫn có thể trùng nhau.

Các kiểm tra trước ghi còn có thể gồm:

| Kiểm tra | Mục tiêu |
|---|---|
| ID/khóa bắt buộc và đúng kiểu | Không tạo mục không thể nhận diện lại |
| Khóa không trùng sau chuẩn hóa | Phát hiện xung đột ngay trong nguồn |
| Trường bắt buộc và giới hạn | Tránh lỗi dữ liệu ở giữa đợt ghi |
| Tham chiếu tồn tại hoặc có trong tập seed | Giữ quan hệ hợp lệ |
| Dataset/version đúng mong đợi | Không nạp nhầm hợp đồng dữ liệu |

Kiểm tra trước ghi giảm lỗi input nhưng không thay ràng buộc dữ liệu. Trạng thái database hoặc một tiến trình khác vẫn có thể thay đổi sau bước kiểm tra.

## 6. Chọn chính sách cho bản ghi đã tồn tại

Các chính sách cần được đặt tên và công bố rõ:

| Chính sách | Khi chưa có | Khi đã có |
|---|---|---|
| Tạo nếu thiếu | Tạo mới | Giữ nguyên dữ liệu hiện tại |
| Tạo hoặc xác minh | Tạo mới | So sánh các trường cần thiết; khác thì báo xung đột |
| Cập nhật trường do fixture quản lý | Tạo mới | Chỉ cập nhật tập trường đã xác định thuộc fixture |
| Đặt lại dữ liệu môi trường cô lập | Theo quy trình riêng | Phải có phạm vi reset rõ ràng |

Không dùng cùng một từ “upsert” để che các quyết định khác nhau. Một thao tác có tên upsert ở backend có thể cập nhật toàn bộ document, một số trường hoặc có điều kiện khác theo API cụ thể.

Nếu người dùng đã sửa tên sản phẩm, fixture cần chọn giữ tên, khôi phục tên seed hoặc báo xung đột. `save` không tự biết ai là chủ thể được phép quyết định trường đó.

Chính sách “tạo hoặc xác minh” hữu ích khi dữ liệu seed là hợp đồng chuẩn cần phát hiện sai lệch. Chính sách “tạo nếu thiếu” hữu ích khi dữ liệu đã được tạo có thể phát triển độc lập sau đó.

Không xóa toàn bộ dữ liệu chỉ để làm một fixture trở nên dễ nạp lại. Reset môi trường là một thao tác riêng với phạm vi và điều kiện riêng.

## 7. Ví dụ tạo hoặc xác minh theo khóa nghiệp vụ

Giả sử `Product` có ID do persistence quản lý, còn `(tenantId, code)` là khóa nghiệp vụ. Repository minh họa:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

interface ProductRepository extends CrudRepository<Product, Long> {

    Optional<Product> findByTenantIdAndCode(UUID tenantId, String code);
}
```

Ví dụ giả định module hỗ trợ derived query này, domain có mapping phù hợp và kho dữ liệu thực thi ràng buộc duy nhất cho cặp tenant/code.

Writer của ứng dụng:

```java
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

enum SeedOutcome {
    CREATED,
    UNCHANGED
}

@Service
class ProductFixtureWriter {

    private final ProductRepository repository;

    ProductFixtureWriter(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public SeedOutcome createOrVerify(UUID tenantId, SeedProduct row) {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(row);

        Optional<Product> existing = repository.findByTenantIdAndCode(
                tenantId, row.code());

        if (existing.isPresent()) {
            Product product = existing.get();
            if (!Objects.equals(product.getTitle(), row.title())) {
                throw new FixtureConflictException(
                        "Dữ liệu hiện có khác fixture tại mã " + row.code());
            }
            return SeedOutcome.UNCHANGED;
        }

        Product product = Product.create(tenantId, row.code(), row.title());
        repository.save(product);
        return SeedOutcome.CREATED;
    }
}

final class FixtureConflictException extends RuntimeException {

    FixtureConflictException(String message) {
        super(message);
    }
}
```

`Product.create(...)`, `getTitle()` và metadata persistence thuộc domain của ứng dụng. Factory được giả định tạo entity mới đúng với cách module nhận diện trạng thái mới; nó không được repository sinh ra chỉ từ tên phương thức.

Ví dụ chủ động chọn transaction riêng cho từng mục và cần transaction manager hỗ trợ propagation tương ứng. Writer phải được gọi qua bean/proxy Spring từ bộ điều phối khác, không phải gọi nội bộ rồi kỳ vọng annotation tự mở transaction mới.

Khi nhận kết quả từ lời gọi qua proxy thành công, bộ điều phối mới ghi nhận mục đã hoàn tất. Lỗi constraint có thể xuất hiện ở lúc flush/commit thay vì ngay tại dòng `save`.

Code chưa tự giải quyết race khi hai tiến trình cùng tạo một khóa chưa có. Phần tiếp theo xử lý điều kiện bắt buộc đó.

## 8. Kiểm tra rồi ghi không tự ngăn chạy đồng thời

Một tình huống điển hình:

```text
Tiến trình A: tìm tenant/code → chưa có.
Tiến trình B: tìm tenant/code → chưa có.
Tiến trình A: tạo mới.
Tiến trình B: cũng tạo mới.
```

Nếu không có ràng buộc duy nhất theo khóa nghiệp vụ, cả hai có thể tạo hai bản ghi với ID persistence khác nhau.

Cần ràng buộc ở nơi lưu trữ với đúng phạm vi khóa. Tùy module, đó có thể là unique constraint, unique index, conditional write hoặc cơ chế tương đương. Annotation mapping chỉ có hiệu lực khi công cụ/schema/index thực tế đã thiết lập đúng ràng buộc đó.

Khi một tiến trình thua do xung đột duy nhất đúng khóa cần bảo vệ, có thể áp dụng chính sách:

1. Để transaction ghi thất bại kết thúc/rollback.
2. Nhận diện đúng loại xung đột và đúng ràng buộc liên quan.
3. Đọc lại đối tượng bằng khóa nghiệp vụ trong một transaction phù hợp mới.
4. Nếu nội dung thỏa chính sách xác minh, coi là đã được tiến trình khác tạo đúng.
5. Nếu nội dung khác, trả xung đột thay vì bỏ qua.

Không bắt mọi lỗi integrity rồi coi đều là “đã tồn tại”. Lỗi còn có thể do khóa ngoại, trường bắt buộc, ràng buộc khác hoặc mapping sai.

Cũng không đọc lại ngay trong một transaction đã bị đánh dấu rollback-only rồi giả định nó sẽ hoạt động như một transaction bình thường. Cách quản lý transaction và exception phải phù hợp module/framework đang dùng.

Optimistic locking trên bản ghi đã có không tự thay ràng buộc duy nhất cho hai lần insert đồng thời khi chưa có bản ghi.

## 9. Transaction toàn đợt hay từng mục?

Hai thiết kế có mục tiêu khác nhau:

| Thiết kế | Đặc điểm |
|---|---|
| Một transaction cho toàn đợt | Có thể rollback toàn bộ theo khả năng kho dữ liệu; đợt lớn có thể giữ tài nguyên lâu |
| Transaction cho từng mục/nhóm | Có tiến độ đã commit; cần chính sách phục hồi sau lỗi giữa chừng |

Writer ở phần 7 chọn từng mục. Nếu mục thứ 3 thất bại, hai mục trước có thể đã commit. Lần chạy sau phải nhận ra chúng là `UNCHANGED`, rồi tiếp tục xử lý phần còn lại theo chính sách.

Đây chính là một lý do cần fixture có khả năng nạp lại. Việc có thể retry không chỉ phục vụ restart bình thường mà còn phục vụ kết quả chưa biết hoặc một đợt bị gián đoạn.

Nếu nghiệp vụ yêu cầu toàn bộ fixture cùng thành công hoặc cùng thất bại, cần một đường thực thi có transaction bao toàn đợt và bỏ thiết kế `REQUIRES_NEW` từng mục. Không kết hợp hai mục tiêu rồi suy ra transaction ngoài có thể rollback mọi commit độc lập ở bên trong.

Đối với nhiều kho dữ liệu, không mặc định một annotation transaction tạo giao dịch phân tán. Cần thiết kế chiến lược nhất quán và phục hồi phù hợp các module tham gia.

`saveAll` cũng không tự là bằng chứng toàn đợt atomic hoặc chỉ có một câu ghi. Phạm vi transaction, batching và hành vi backend phải được xác định riêng.

## 10. ID cố định vẫn phải hiểu newness và save

Một fixture dùng ID gán trước có thể giảm việc tra cứu theo khóa nghiệp vụ, nhưng cần hiểu cách module quyết định entity mới.

Các yếu tố có thể tham gia gồm:

```text
ID null hoặc đã có.
Version null/giá trị ban đầu.
EntityInformation của module.
Persistable.isNew() nếu ứng dụng dùng hợp đồng đó.
Cơ chế insert/merge/update của repository implementation.
```

Do đó, cùng một object có ID cố định không tự luôn được upsert theo cách mong muốn. Nó có thể tạo insert trùng khóa, update dữ liệu cũ hoặc gặp optimistic locking tùy metadata và module.

Không giải quyết bằng cách đặt `isNew()` luôn trả true. Cách đó có thể khiến mỗi lần nạp lại tiếp tục cố insert cùng ID.

Cũng không chép version từ một fixture cũ sang entity đang có rồi lưu mà không hiểu ngữ nghĩa. Version là metadata kiểm soát cạnh tranh, không chỉ một trường dữ liệu mẫu tùy ý.

Nếu cần ID do repository sinh để tạo quan hệ tiếp theo, hãy sử dụng kết quả trả về của `save` và hợp đồng của module. Đừng suy ra object đầu vào luôn được sửa theo cùng cách ở mọi implementation.

## 11. Quan hệ giữa các mục cũng cần khóa ổn định

Một fixture sản phẩm có thể tham chiếu danh mục theo mã nguồn ổn định:

```json
{
  "code": "BOOK-SPRING",
  "title": "Spring Data cơ bản",
  "categoryCode": "BOOKS"
}
```

Nếu ID danh mục được persistence sinh, `categoryCode` giúp bộ nạp tra đúng danh mục đã có thay vì hard-code một ID khác nhau giữa các môi trường.

Trình tự có thể là:

```text
Kiểm tra toàn bộ mã và tham chiếu.
    → tạo/xác minh danh mục.
    → tra ID/domain danh mục theo khóa ổn định.
    → tạo/xác minh sản phẩm.
```

Không giả định repository populator tự giải mọi business key trong JSON thành quan hệ persistence. Domain mapping, aggregate boundary và cascade của từng module vẫn quyết định điều gì được lưu.

Nếu có quan hệ vòng hoặc yêu cầu cập nhật nhiều bước, cần quy trình import riêng với trạng thái trung gian hợp lệ. Chỉ đổi thứ tự các object trong file có thể không đủ để giải bài toán.

Khi đổi mã nguồn của một mục đã được tham chiếu, cần xử lý như một thay đổi định danh. Nếu coi mã mới là mục hoàn toàn mới, có thể để lại mục cũ và tạo các tham chiếu không như dự định.

## 12. Phiên bản fixture và phạm vi trường do fixture quản lý

Khả năng chạy lại cùng một version không đồng nghĩa mọi version mới nên ghi đè toàn bộ dữ liệu cũ.

Ví dụ fixture version 2 chỉ thay tiêu đề mẫu, còn người dùng đã bổ sung mô tả riêng. Chính sách cần xác định tiêu đề và mô tả thuộc ai quản lý.

Một cách phân chia:

| Loại trường | Chính sách có thể chọn |
|---|---|
| Khóa định danh ổn định | Không đổi tùy ý giữa các lần chạy |
| Trường do fixture quản lý | Chỉ cập nhật khi fixture được phép và giá trị cần đổi |
| Trường do người dùng quản lý | Giữ nguyên khi nạp lại |
| Metadata audit/version | Xử lý theo chính sách framework và nghiệp vụ |

Có thể lưu thông tin dataset/version hoặc nguồn sở hữu trong trạng thái khởi tạo của ứng dụng. Nếu dùng checksum, cần xác định nội dung nào được băm và sự khác nhau nào có ý nghĩa; thay đổi khoảng trắng của file không nhất thiết là thay đổi nghiệp vụ.

Một bản ghi “đã hoàn tất version 2” chỉ nên được ghi nhận sau khi các điều kiện hoàn tất thực sự đạt. Nếu đánh dấu trước rồi lỗi giữa chừng, lần khởi động sau có thể bỏ qua dữ liệu còn thiếu.

Marker version cũng không thay unique constraint hoặc chính sách chống hai tiến trình chạy cùng lúc. Nó là một phần của quy trình điều phối, không phải bằng chứng duy nhất rằng trạng thái thực tế đúng.

## 13. Auditing và tác dụng phụ khi chạy lại

Một lần `save` không cần thiết có thể đi qua callbacks, entity listeners hoặc auditing theo module. Dù thuộc tính nghiệp vụ không đổi, metadata hoặc tác dụng phụ vẫn có thể khác.

Vì vậy, với mục đã đúng và chính sách giữ nguyên, writer ở phần 7 trả `UNCHANGED` mà không gọi save thêm.

Các điều cần xác định khi seed:

- Danh tính hệ thống nào được dùng làm auditor lúc startup.
- Trường tạo mới và sửa đổi được framework xử lý ra sao.
- Có phát event, ghi outbox hoặc gọi dịch vụ ngoài khi một mục được lưu không.
- Tác dụng phụ có cần khóa chống xử lý lặp riêng không.

Nếu một tác dụng phụ đã xảy ra nhưng tiến trình dừng trước khi ghi nhận hoàn tất, lần chạy sau có thể thực hiện lại. Khả năng nhận diện lại entity không tự bảo đảm một email hoặc một lời gọi ngoài chỉ được thực hiện một lần.

Đối với dữ liệu khởi tạo, nên xác định rõ đường nghiệp vụ được dùng. Lưu thẳng qua repository không tự gọi toàn bộ service, trong khi gọi service lại có thể kích hoạt thêm hành vi mà fixture cần kiểm soát.

## 14. Theo dõi kết quả và readback theo khóa

Một báo cáo đợt nạp có thể phân biệt:

```text
CREATED: mục mới đã được xử lý thành công.
UNCHANGED: mục đã tồn tại và đáp ứng chính sách xác minh.
CONFLICT: mục tồn tại nhưng không thỏa chính sách.
FAILED: không hoàn tất vì lỗi dữ liệu hoặc hạ tầng.
```

Bộ điều phối cần chỉ ghi nhận hoàn tất sau khi ranh giới transaction tương ứng thành công. Một dòng log trước commit không phải bằng chứng bền vững.

Sau đợt nạp, có thể kiểm tra theo các khóa nghiệp vụ và thuộc tính quan trọng. Chỉ nhìn `count()` dễ bỏ sót các tình huống:

| Tổng số có vẻ đúng nhưng dữ liệu sai | Ví dụ |
|---|---|
| Có bản ghi trùng và thiếu bản ghi khác | Tổng số vẫn bằng số mục dự kiến |
| Có dữ liệu của tenant khác | Truy vấn kiểm tra chưa đúng phạm vi |
| Tiêu đề hoặc quan hệ sai | Đếm số lượng không phát hiện |
| Marker hoàn tất nhưng mục chưa commit | Trạng thái điều phối không khớp dữ liệu |

Readback cần đi qua đúng kho dữ liệu/module và đúng phạm vi tenant. Với hệ thống có độ trễ đọc hoặc mô hình nhất quán riêng, cần xác định điều kiện xác minh phù hợp thay vì suy ra mọi lần đọc ngay đều có cùng bảo đảm.

Không tự động xóa những mục “không có trong fixture mới” nếu hợp đồng chỉ là nạp thêm hoặc xác minh. Đồng bộ xóa là một chính sách riêng cần có phạm vi sở hữu dữ liệu rõ ràng.

## 15. Quan hệ với repository populator có sẵn

Repository populator đọc JSON/XML và lưu domain object hữu ích cho fixture đơn giản. Tuy nhiên, bản thân cơ chế đọc resource không tự cung cấp mọi chính sách ở bài này.

| Nhu cầu | Cần xác định thêm |
|---|---|
| Tránh duplicate business key | Khóa ổn định và ràng buộc dữ liệu |
| Giữ thay đổi của người dùng | Chính sách trường và xử lý đối tượng đã có |
| Chạy lại sau lỗi | Transaction và khả năng nhận diện mục đã hoàn tất |
| Nhiều instance khởi động | Điều phối và xử lý xung đột duy nhất |
| Version fixture | Quy tắc nâng cấp và ghi nhận hoàn tất |
| Quan hệ theo mã nguồn | Bước tra cứu/chuyển tham chiếu phù hợp |

Nếu fixture chỉ cần object cố định với mapping đơn giản, có thể dùng populator cùng các điều kiện phù hợp. Nếu cần tạo/xác minh theo business key, quyền sở hữu trường hoặc báo cáo xung đột, một reader kết hợp service import tường minh thường thể hiện hợp đồng rõ hơn.

Schema input cho service import có thể là DTO riêng của ứng dụng; không bắt buộc mang `_class` của JSON repository reader. Ngược lại, không đưa một wrapper DTO tự định nghĩa vào populator rồi mặc định nó biết cách tìm repository cho từng mục bên trong.

## 16. Tình huống kiểm chứng khả năng nạp lại

| Kịch bản | Kết quả cần đạt theo chính sách tạo hoặc xác minh |
|---|---|
| Lần đầu trên tập dữ liệu chưa có các khóa | Tạo đủ các mục hợp lệ |
| Lần hai với cùng fixture | Không tăng số mục cùng khóa; các mục đúng là UNCHANGED |
| Hai mã chỉ khác hoa/thường theo quy tắc chuẩn hóa | Phát hiện trùng ngay ở bước kiểm tra nguồn |
| Trùng khóa giữa hai resource | Không ghi mơ hồ theo thứ tự ngẫu nhiên |
| Dữ liệu cũ khác nội dung cần xác minh | Báo xung đột, không âm thầm ghi đè |
| Lỗi ở mục giữa đợt theo transaction từng mục | Lần sau nhận diện các mục đã commit và xử lý phần còn lại |
| Hai instance cùng tạo một khóa | Ràng buộc dữ liệu ngăn duplicate; kết quả xung đột được xử lý đúng |
| Cùng code ở hai tenant hợp lệ | Không nhận nhầm là cùng một đối tượng |
| Đổi version fixture | Theo chính sách nâng cấp đã công bố |
| Một mục có quan hệ đến danh mục | Tham chiếu đúng đối tượng sau mọi lần chạy |
| Mục UNCHANGED | Không tạo thêm thao tác lưu/tác dụng phụ ngoài chính sách |
| Dataset marker báo hoàn tất | Readback dữ liệu và trạng thái điều phối khớp nhau |

Các kịch bản cần kiểm tra trạng thái và nội dung theo khóa, không chỉ kiểm tra không có exception. Một đợt chạy im lặng nhưng tạo duplicate vẫn là kết quả sai.

## 17. Bài tập tự kiểm tra

### Tình huống 1: Mỗi lần startup tạo UUID mới cho cùng một danh mục

Repository lưu thành công mọi lần và không có lỗi trùng primary key.

**Phân tích:** định danh persistence khác nhau không ngăn trùng đối tượng nghiệp vụ. Cần ID fixture ổn định hoặc tra cứu bằng khóa nghiệp vụ trước khi tạo, cùng ràng buộc dữ liệu tương ứng.

### Tình huống 2: Đã existsById nên cho rằng không có race

Hai instance cùng thấy chưa có dữ liệu rồi cùng ghi.

**Phân tích:** kiểm tra và ghi là hai bước có thể xen kẽ. Cần ràng buộc ở nơi lưu trữ và quy trình xử lý xung đột/đọc lại đúng transaction.

### Tình huống 3: ID cố định nhưng isNew luôn true

Lần nạp lại tiếp tục cố insert cùng ID.

**Phân tích:** phải hiểu cơ chế nhận diện entity mới của module. ID ổn định không tự sửa một hợp đồng `Persistable` hoặc metadata newness sai.

### Tình huống 4: Tăng version fixture bằng cách thay version trong mọi ID

Các đối tượng logic cũ vẫn còn, còn bộ ID mới được tạo thêm.

**Phân tích:** đổi ID đã tạo đối tượng khác. Version quản lý thay đổi nên được phân biệt với định danh ổn định của đối tượng cần cập nhật/xác minh.

### Tình huống 5: Ghi marker hoàn tất trước khi xử lý các mục

Đợt nạp lỗi giữa chừng nhưng lần startup sau bỏ qua vì marker đã có.

**Phân tích:** trạng thái hoàn tất không khớp công việc thực tế. Cần ghi nhận sau điều kiện hoàn tất và có chính sách phục hồi cho đợt dang dở.

### Tình huống 6: Mọi mục được gọi save dù nội dung không đổi

Dữ liệu nghiệp vụ có vẻ ổn định nhưng audit hoặc event tiếp tục thay đổi qua các lần nạp.

**Phân tích:** cần xác định phạm vi idempotency gồm những tác động nào. Nếu chính sách là giữ nguyên mục đã đúng, hãy phát hiện UNCHANGED và tránh thao tác ghi không cần thiết.

Fixture có thể nạp lại cần nhiều hơn một tập ID không trùng trong file. Hãy giữ định danh logic ổn định, chuẩn hóa và kiểm tra nguồn trước khi ghi, chọn chính sách cho dữ liệu đã có, rồi dùng transaction và ràng buộc của module để duy trì chính sách ấy cả khi chạy lại hoặc chạy đồng thời.
