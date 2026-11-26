# Quản lý thay đổi lược đồ và ngăn truy cập trực tiếp dữ liệu ngoài ranh giới

Trong chương **Tầng truy cập dữ liệu**, bài học này tập trung vào hai trách nhiệm gắn liền với độ bền vững của dữ liệu: quản lý thay đổi lược đồ cơ sở dữ liệu có kiểm soát và bảo vệ ranh giới truy cập dữ liệu của ứng dụng. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là tổ chức phần mềm theo kiến trúc phân tầng, trong đó mỗi tầng có trách nhiệm rõ ràng và tầng truy cập dữ liệu che giấu cơ chế lưu trữ cụ thể khỏi các phần còn lại.

Lược đồ cơ sở dữ liệu luôn thay đổi khi sản phẩm phát triển: thêm thuộc tính, đổi quy tắc ràng buộc, tách bảng, tạo chỉ mục hoặc chuyển đổi dữ liệu cũ. Nếu thay đổi được thực hiện thủ công, không có lịch sử và không phối hợp với phiên bản ứng dụng, môi trường phát triển, kiểm thử và production có thể dần khác nhau. Đồng thời, nếu controller, tầng nghiệp vụ hoặc module khác tự mở kết nối và truy vấn các bảng tùy ý, cấu trúc lưu trữ sẽ rò rỉ ra toàn hệ thống. Một thay đổi nhỏ trong schema khi đó có thể buộc nhiều thành phần không liên quan phải sửa.

Sau bài học, bạn có thể:

- Quản lý schema bằng migration có phiên bản, được lưu cùng mã nguồn và áp dụng có thể kiểm soát.
- Lập kế hoạch thay đổi tương thích giữa phiên bản ứng dụng đang chạy và schema mới.
- Phân biệt migration schema, migration dữ liệu và thay đổi mô hình nghiệp vụ.
- Đặt truy vấn, mapping và thao tác lưu trữ sau hợp đồng của tầng truy cập dữ liệu.
- Dùng quyền cơ sở dữ liệu, cấu trúc module và kiểm thử kiến trúc để ngăn truy cập trực tiếp ngoài ranh giới.
- Kiểm thử migration, chuẩn bị triển khai và xử lý sự cố thay đổi schema.

## 1. Vì sao schema cần được quản lý như một phần của mã nguồn?

Schema mô tả cấu trúc và các quy tắc được cơ sở dữ liệu bảo đảm, chẳng hạn:

- Bảng, cột, kiểu dữ liệu, giá trị mặc định và khả năng nhận `NULL`.
- Khóa chính, khóa ngoại, ràng buộc duy nhất và ràng buộc kiểm tra.
- Chỉ mục, view, sequence, trigger và các đối tượng phụ trợ khác.
- Quan hệ giữa dữ liệu, quy tắc toàn vẹn và một số chính sách lưu trữ.

Khi một ứng dụng chuyển từ `customer.name` sang lưu riêng `first_name` và `last_name`, thay đổi không chỉ nằm ở câu lệnh SQL. Nó ảnh hưởng đến dữ liệu hiện có, mã Java, truy vấn báo cáo, API nội bộ, job nền và có thể cả các ứng dụng khác đang đọc cùng database. Cần biết thay đổi nào đã được áp dụng ở từng môi trường, thứ tự thực hiện và phiên bản ứng dụng nào tương thích với schema đó.

Quản lý migration trong repository giúp mỗi thay đổi có lịch sử, được review và có thể chạy lại một cách nhất quán trên môi trường mới. Đây là cách biến schema thành một phần có thể kiểm soát của quá trình phát triển phần mềm thay vì một tài sản chỉ được sửa bằng thao tác thủ công trên từng database.

Migration không thay thế việc sao lưu, giám sát hoặc quy trình phát hành. Nó cung cấp cách mô tả và áp dụng thay đổi; việc triển khai vẫn phải tính đến dữ liệu thực tế, tải hệ thống, khóa bảng, thời gian chạy và khả năng tương thích.

## 2. Trách nhiệm của tầng truy cập dữ liệu

Tầng truy cập dữ liệu chịu trách nhiệm chuyển yêu cầu đọc/ghi của ứng dụng thành thao tác trên cơ chế lưu trữ cụ thể. Tùy hệ thống, nó có thể chứa:

- Repository hoặc DAO thực hiện truy vấn và cập nhật dữ liệu.
- Adapter triển khai các cổng (port) mà tầng ứng dụng sử dụng.
- Mapping giữa mô hình ứng dụng/nghiệp vụ với entity hoặc record lưu trữ.
- Câu SQL, cấu hình ORM, kết nối, phân trang và tối ưu truy vấn.
- Thành phần đọc dữ liệu chuyên biệt, chẳng hạn query adapter hoặc read model.
- Công cụ migration schema và dữ liệu, cùng quy trình áp dụng chúng.

Không phải mọi dự án đều phải có đúng một package mang tên `data-access`. Một ứng dụng nhỏ có thể đặt repository cùng module nghiệp vụ; một hệ thống lớn có thể tách adapter theo database hoặc bounded context. Điều quan trọng là xác định nơi sở hữu thao tác lưu trữ và kiểm soát những thành phần được phép phụ thuộc vào chi tiết đó.

Tầng trình bày không nên tự tạo SQL để đọc bảng đơn hàng. Tầng nghiệp vụ không nên biết tên cột hoặc cách cấu hình Hibernate. Một module khác không nên truy cập trực tiếp bảng nội bộ của module này chỉ vì database cho phép. Những thành phần đó nên sử dụng hợp đồng do chủ sở hữu dữ liệu công bố, chẳng hạn một ca sử dụng, repository port, API hoặc read model được thiết kế cho mục đích chia sẻ.

## 3. Migration có phiên bản

Migration là một thay đổi có tên và thứ tự xác định, mô tả cách chuyển schema hoặc dữ liệu từ trạng thái trước sang trạng thái sau. Các công cụ như Flyway và Liquibase hỗ trợ quản lý lịch sử migration, phát hiện thay đổi đã áp dụng và thực hiện migration theo quy tắc cấu hình.

Với Flyway, migration dạng SQL thường được đặt tên theo phiên bản, ví dụ:

~~~text
src/main/resources/db/migration/
  V001__create_customer_table.sql
  V002__add_customer_status.sql
  V003__create_customer_email_index.sql
~~~

Một migration có phiên bản có thể chứa SQL như sau:

~~~sql
-- V002__add_customer_status.sql
ALTER TABLE customer
    ADD COLUMN status VARCHAR(20);

UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE customer
    ALTER COLUMN status SET NOT NULL;
~~~

Ví dụ này minh họa một thay đổi nhỏ trên PostgreSQL; cú pháp và mức độ khóa phụ thuộc hệ quản trị cơ sở dữ liệu. Với bảng lớn, việc thêm cột, cập nhật toàn bộ dữ liệu và đặt `NOT NULL` trong một migration có thể tạo khóa hoặc tải lớn. Khi đó nên chia thành nhiều bước triển khai an toàn hơn, thay vì áp dụng nguyên ví dụ này cho mọi quy mô.

Các nguyên tắc quan trọng:

1. Migration phải được lưu trong kiểm soát phiên bản và review như mã nguồn.
2. Mỗi migration có thứ tự ổn định và mô tả một thay đổi có ý nghĩa.
3. Migration đã áp dụng ở môi trường dùng chung nên được xem là bất biến. Nếu cần sửa, tạo migration mới để tiến schema lên trạng thái đúng.
4. Không sửa lịch sử migration để làm cho một môi trường cá biệt chạy được; hãy tìm nguyên nhân sai lệch và bổ sung thay đổi có kiểm soát.
5. Kiểm tra công cụ migration báo thành công và lịch sử schema ghi nhận đúng phiên bản.

Flyway thường lưu lịch sử trong bảng `flyway_schema_history`. Liquibase có cơ chế theo dõi change set riêng. Không nên đồng thời để nhiều công cụ hoặc nhiều pipeline không phối hợp cùng quản lý một schema vì chúng có thể không hiểu trạng thái của nhau.

### Cấu hình áp dụng migration

Trong ứng dụng Spring Boot, Flyway có thể tự động áp dụng migration khi ứng dụng khởi động nếu dependency và cấu hình được bật. Một số hệ thống chọn chạy migration thành bước riêng trong pipeline phát hành để kiểm soát quyền, thứ tự và thời gian thực hiện. Ví dụ cấu hình tối giản:

~~~properties
spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration
~~~

Đây là cấu hình tham khảo. Việc bật migration trong mọi instance ứng dụng có thể không phù hợp nếu nhiều instance khởi động đồng thời, cần tài khoản database đặc quyền riêng hoặc migration kéo dài. Với production, nhiều nhóm tách tài khoản migration có quyền DDL khỏi tài khoản runtime chỉ có quyền cần thiết để đọc/ghi dữ liệu.

## 4. Thay đổi schema và dữ liệu theo từng giai đoạn

Thay đổi schema có thể phá vỡ phiên bản ứng dụng đang chạy. Ví dụ, ứng dụng cũ đọc cột `name`, trong khi phiên bản mới muốn dùng `display_name`. Nếu xóa `name` trước khi tất cả instance cũ ngừng chạy, request đang xử lý hoặc instance chưa được cập nhật có thể lỗi.

Một kỹ thuật hữu ích là **expand–migrate–contract**:

1. **Expand – mở rộng schema:** thêm cấu trúc mới theo cách vẫn tương thích với ứng dụng hiện tại, ví dụ thêm cột `display_name` có thể nhận `NULL`.
2. **Migrate – chuyển dữ liệu và ứng dụng:** cập nhật dữ liệu cũ sang cấu trúc mới; phát hành ứng dụng có thể đọc/ghi theo giai đoạn chuyển tiếp. Nếu cần, tạm thời ghi đồng thời hai cột hoặc đọc cột mới rồi fallback cột cũ.
3. **Contract – thu hẹp schema:** sau khi xác nhận không còn phiên bản hoặc consumer nào dùng cột cũ, ngừng ghi cột cũ rồi mới xóa cột và mã tương thích.

Ví dụ thay `customer.name` bằng `customer.display_name` có thể triển khai như sau:

| Giai đoạn | Schema | Ứng dụng |
|---|---|---|
| Ban đầu | Chỉ có `name` | Phiên bản cũ đọc/ghi `name`. |
| Expand | Thêm `display_name`, giữ `name` | Phiên bản cũ vẫn chạy; phiên bản mới có thể ghi cả hai. |
| Migrate | Hai cột cùng tồn tại, dữ liệu được backfill | Phiên bản mới ưu tiên `display_name`, xử lý fallback nếu cần. |
| Contract | Sau khi mọi consumer đã chuyển, bỏ `name` | Mã mới chỉ dùng `display_name`. |

Không phải thay đổi nào cũng cần cả ba giai đoạn. Một thay đổi chỉ thêm chỉ mục hoặc thêm bảng mới chưa được sử dụng có thể đơn giản hơn. Nhưng khi đổi tên, đổi kiểu, xóa cột, thay khóa hoặc biến đổi dữ liệu đang được nhiều phiên bản ứng dụng sử dụng, cần nghĩ đến thời gian tồn tại đồng thời của các phiên bản.

### Backfill dữ liệu lớn

Một lệnh `UPDATE` toàn bảng có thể phù hợp với bảng nhỏ, nhưng trên bảng lớn có thể gây transaction dài, khóa kéo dài, tăng log giao dịch và ảnh hưởng truy vấn đang chạy. Có thể chuyển dữ liệu theo batch với giới hạn kích thước, theo khóa tăng dần hoặc theo phạm vi thời gian. Quy trình backfill cần:

- Có thể tiếp tục từ checkpoint sau khi bị dừng.
- Xử lý được bản ghi mới phát sinh trong lúc backfill.
- Có cách phát hiện và sửa các bản ghi chưa chuyển thành công.
- Có thống kê số lượng, tỷ lệ lỗi và thời gian thực hiện.
- Chỉ cho phép bước contract sau khi dữ liệu và consumer đã được xác minh.

Nếu backfill được thực hiện bởi job ứng dụng thay vì migration DDL, cần ghi nhận rõ bước nào chạy trước/sau và cách xác định rằng backfill đã hoàn tất. Không nên để bước xóa dữ liệu cũ phụ thuộc vào một giả định không được kiểm tra.

## 5. Thiết kế migration an toàn

Migration có thể thay đổi cấu trúc, chuyển dữ liệu hoặc bổ sung ràng buộc. Mỗi loại có rủi ro khác nhau.

### Thêm cột và ràng buộc

Khi thêm trường bắt buộc vào bảng đang có dữ liệu, cần xác định giá trị cho các bản ghi cũ. Một cách triển khai an toàn thường là thêm cột nullable, cập nhật dữ liệu, xác nhận không còn giá trị thiếu rồi mới đặt `NOT NULL`. Với hệ quản trị hỗ trợ cách thêm constraint chưa kiểm tra toàn bộ dữ liệu ngay, có thể dùng để giảm thời gian khóa; cú pháp cụ thể cần theo tài liệu của database đang dùng.

Không nên thêm giá trị mặc định chỉ để migration qua được nếu giá trị đó không đúng về mặt nghiệp vụ. Dữ liệu mặc định sai có thể tạo ra trạng thái hợp lệ về mặt SQL nhưng sai nghĩa trong ứng dụng.

### Đổi kiểu hoặc thu hẹp dữ liệu

Trước khi đổi `VARCHAR(200)` thành `VARCHAR(50)`, cần đo độ dài dữ liệu hiện tại và xác định cách xử lý giá trị vượt giới hạn. Trước khi đổi số thập phân sang số nguyên hoặc thay đơn vị đo, cần định nghĩa quy tắc chuyển đổi và sai số được chấp nhận. Không nên dựa vào việc database tự ép kiểu mà không xác minh ý nghĩa dữ liệu.

### Chỉ mục và ràng buộc duy nhất

Chỉ mục giúp tăng tốc truy vấn nhưng có chi phí ghi và lưu trữ. Trước khi thêm chỉ mục, xác định truy vấn nào cần hỗ trợ, thứ tự cột, độ chọn lọc và tác động trên workload thực tế. Một số database hỗ trợ tạo chỉ mục đồng thời để giảm chặn ghi, nhưng thao tác có thể không chạy được bên trong transaction thông thường; cần kiểm tra yêu cầu của công cụ migration và hệ quản trị.

Ràng buộc duy nhất có thể thất bại nếu dữ liệu hiện tại đã có trùng lặp. Trước khi thêm constraint, hãy tìm và giải quyết dữ liệu vi phạm. Không nên xóa bản ghi trùng một cách tự động nếu chưa xác định quy tắc chọn bản ghi chính xác.

### Khóa ngoại và xóa dữ liệu

Khóa ngoại giúp bảo đảm tham chiếu hợp lệ. Khi thêm khóa ngoại cho bảng lớn, cần xác định tác động khóa và chiến lược kiểm tra dữ liệu cũ. Các hành vi `ON DELETE CASCADE`, `SET NULL` hoặc `RESTRICT` có ý nghĩa nghiệp vụ khác nhau; không chọn cascade chỉ vì nó tiện khi xóa.

Xóa cột hoặc bảng thường là bước rủi ro cao hơn thêm mới. Hãy xác minh không còn ứng dụng, báo cáo, job, view, trigger hoặc consumer nào phụ thuộc trước khi loại bỏ. Trong môi trường có nhiều phiên bản chạy đồng thời, cần chờ hết thời gian chuyển tiếp trước khi contract.

## 6. Ngăn truy cập dữ liệu trực tiếp ngoài ranh giới

Giả sử controller thực hiện truy vấn như sau:

~~~java
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {
    private final JdbcTemplate jdbc;

    CustomerController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/customers/{id}")
    Map<String, Object> get(@PathVariable UUID id) {
        return jdbc.queryForMap(
                "select id, email from customer where id = ?", id);
    }
}
~~~

Đoạn code này khiến tầng trình bày biết tên bảng, tên cột và công nghệ JDBC. Nếu schema đổi hoặc cách lưu trữ được thay bằng JPA hay một dịch vụ khác, controller phải sửa. Các truy vấn tương tự có thể xuất hiện trong nhiều nơi, dẫn đến logic đọc/ghi phân tán, quyền truy cập khó kiểm soát và kiểm thử phụ thuộc vào database.

Có thể đặt thao tác sau một hợp đồng ứng dụng và một adapter dữ liệu:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

public interface FindCustomer {
    CustomerView execute(UUID customerId);
}

public record CustomerView(UUID id, String email) {}

public interface CustomerReader {
    Optional<CustomerRecord> findById(UUID customerId);
}

@Service
class FindCustomerService implements FindCustomer {
    private final CustomerReader customers;

    FindCustomerService(CustomerReader customers) {
        this.customers = customers;
    }

    @Override
    public CustomerView execute(UUID customerId) {
        var customer = customers.findById(customerId)
                .orElseThrow(CustomerNotFoundException::new);
        return new CustomerView(customer.id(), customer.email());
    }
}
~~~

Adapter JPA hoặc JDBC triển khai `CustomerReader` và chịu trách nhiệm chuyển đổi dữ liệu lưu trữ thành kiểu mà tầng ứng dụng sử dụng. Controller chỉ gọi `FindCustomer`, sau đó chuyển `CustomerView` thành response HTTP. Cấu trúc cụ thể có thể khác, nhưng consumer không cần biết câu SQL hoặc entity ORM.

Không phải mọi truy vấn đều bắt buộc phải đi qua một interface mới. Nếu module nhỏ và repository hiện có đã là ranh giới công khai hợp lý, có thể dùng trực tiếp repository đó từ tầng ứng dụng. Mục tiêu là ngăn các tầng không sở hữu dữ liệu truy cập tùy ý vào chi tiết lưu trữ, không phải tạo thêm lớp trung gian cho mọi câu lệnh.

## 7. Kiểm soát quyền sở hữu và quyền truy cập dữ liệu

Ranh giới trong mã nguồn cần được củng cố bằng quy tắc sở hữu và quyền thực thi:

### Quyền sở hữu schema

Mỗi module hoặc dịch vụ nên có trách nhiệm rõ ràng với các bảng mà nó sở hữu. Module khác không nên tự ý thay đổi schema của chủ sở hữu. Nếu cần dữ liệu, hãy sử dụng API, sự kiện, read model được công bố hoặc một hợp đồng tích hợp có chủ đích.

Một số hệ thống dùng chung một database cho nhiều module để đơn giản vận hành. Điều đó không có nghĩa tất cả module được phép sửa mọi bảng. Có thể phân vùng theo schema, tài khoản database hoặc quy ước sở hữu. Nếu nhiều module cùng ghi một bảng, cần có một chủ sở hữu chịu trách nhiệm về schema, quy tắc toàn vẹn và thay đổi tương thích.

### Quyền database tối thiểu

Tài khoản runtime của ứng dụng thường chỉ cần quyền đọc/ghi trên các bảng hoặc schema cần thiết. Quyền tạo bảng, xóa bảng, sửa cấu trúc và quản lý role nên thuộc tài khoản migration hoặc quy trình triển khai riêng. Giảm quyền giúp ngăn một lỗi ở ứng dụng vô tình thực hiện DDL hoặc truy cập bảng không thuộc phạm vi.

Tài khoản database riêng theo module hoặc dịch vụ có thể giúp giới hạn phạm vi ảnh hưởng. Tuy nhiên, cần cân nhắc chi phí quản trị connection, secret và vận hành. Quyền database là lớp phòng vệ bổ sung; nó không thay thế việc thiết kế hợp đồng và kiểm soát phụ thuộc trong mã nguồn.

### Cấu trúc package/module

Có thể giới hạn truy cập bằng package-private, module Java, dependency rule hoặc quy ước module. Ví dụ, entity JPA và repository triển khai được giữ trong package adapter; chỉ hợp đồng ứng dụng hoặc service được công bố ra ngoài. Một bài kiểm tra kiến trúc có thể phát hiện controller phụ thuộc trực tiếp vào package `persistence` hoặc `infra`.

Không nên chỉ dựa vào tên package để khẳng định ranh giới đã được bảo vệ. Nếu mọi lớp đều `public`, mọi module đều có thể import repository và mọi tài khoản đều có quyền DDL, ranh giới chỉ tồn tại trên tài liệu. Hãy kết hợp cấu trúc mã nguồn, kiểm thử kiến trúc, review và quyền database phù hợp.

## 8. Chia sẻ dữ liệu giữa module và hệ thống

Một nhu cầu phổ biến là module A cần đọc dữ liệu mà module B sở hữu. Truy cập trực tiếp bảng của B có vẻ nhanh, nhưng tạo phụ thuộc vào schema và chu kỳ phát hành của B. Khi B đổi tên cột hoặc tách bảng, A có thể hỏng dù hợp đồng nghiệp vụ không thay đổi.

Các lựa chọn thường gặp:

| Cách chia sẻ | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Gọi API/hợp đồng ứng dụng của chủ sở hữu | Cần hành vi hoặc dữ liệu mới nhất theo quy tắc của module sở hữu | Có chi phí gọi, độ trễ và phụ thuộc tính sẵn sàng. |
| Sự kiện và read model riêng | Consumer cần dữ liệu đọc rộng hoặc cập nhật bất đồng bộ | Cần xử lý eventual consistency, thứ tự và message trùng. |
| View hoặc truy vấn báo cáo được công bố | Cần đọc phục vụ báo cáo và hai bên thống nhất hợp đồng dữ liệu | Cần chủ sở hữu duy trì view và quy tắc tương thích. |
| Truy cập trực tiếp bảng nội bộ | Chỉ trong trường hợp được thiết kế và quản trị rõ ràng | Phụ thuộc schema mạnh; cần chủ sở hữu, quyền và chính sách thay đổi cụ thể. |

Không có một lựa chọn phù hợp cho mọi tình huống. Điều quan trọng là không để việc truy cập trực tiếp phát sinh tự phát. Hãy xác định ai sở hữu dữ liệu, ai chịu trách nhiệm thay đổi schema, mức nhất quán cần thiết và cách consumer được thông báo khi hợp đồng thay đổi.

## 9. Quy trình triển khai migration

Một quy trình phát hành migration có thể gồm các bước:

1. Viết migration mới cùng mã nguồn và mô tả tác động đến schema, dữ liệu, khóa và thời gian dự kiến.
2. Review SQL và kiểm thử migration trên database tạm hoặc môi trường tích hợp có phiên bản engine tương thích.
3. Chạy thử nâng cấp từ schema của phiên bản đang dùng, không chỉ tạo database mới từ đầu.
4. Kiểm tra dữ liệu đại diện, truy vấn quan trọng và tương thích với phiên bản ứng dụng cũ/mới.
5. Chuẩn bị backup hoặc phương án phục hồi phù hợp với mức độ rủi ro; xác định cách theo dõi tiến trình và điều kiện dừng.
6. Chạy migration theo thứ tự phát hành đã định, với quyền và khóa điều phối phù hợp để tránh nhiều pipeline cùng sửa schema.
7. Xác nhận migration history, tính toàn vẹn dữ liệu, lỗi ứng dụng, độ trễ và tải database sau triển khai.
8. Chỉ thực hiện bước contract sau khi đã xác nhận không còn consumer cần schema cũ.

Migration có thể không rollback an toàn sau khi đã chuyển đổi dữ liệu hoặc xóa thông tin. Với nhiều thay đổi, cách khôi phục tốt hơn có thể là migration tiến về phía trước để sửa lỗi (forward fix), khôi phục backup hoặc chuyển ứng dụng về phiên bản tương thích với schema hiện tại. Hãy quyết định trước cách phục hồi; không mặc định mọi migration đều có thể đảo ngược chỉ bằng một câu lệnh `down`.

### Tránh chạy migration cạnh tranh

Nếu mỗi instance ứng dụng tự chạy migration khi khởi động, công cụ cần cơ chế khóa hoặc điều phối để tránh hai tiến trình cùng thực hiện. Dù công cụ có hỗ trợ khóa, pipeline vẫn cần bảo đảm chỉ một luồng phát hành chịu trách nhiệm thay đổi schema tại một thời điểm. Migration dài nên được thực hiện như một bước triển khai có giám sát thay vì để nhiều instance cùng khởi động và chờ.

## 10. Kiểm thử migration và ranh giới dữ liệu

Kiểm thử nên bao gồm cả việc schema chuyển đúng trạng thái và việc ứng dụng chỉ truy cập dữ liệu qua ranh giới đã định:

| Loại kiểm thử | Nội dung | Ví dụ |
|---|---|---|
| Migration test | Schema cũ được nâng cấp thành công | Khởi tạo database ở phiên bản trước, chạy migration và xác nhận bảng/cột/constraint mới. |
| Fresh install test | Có thể dựng schema mới từ đầu | Chạy toàn bộ migration trên database rỗng. |
| Data migration test | Dữ liệu cũ được chuyển đúng | Tạo bản ghi có nhiều dạng dữ liệu, chạy backfill và xác nhận kết quả theo quy tắc. |
| Repository integration test | Adapter đọc/ghi đúng trên database thực tế | Lưu và truy vấn qua JPA/JDBC với cùng engine hoặc engine tương thích. |
| Architecture test | Không có phụ thuộc ngoài ranh giới | Controller không import package repository/JPA; module consumer không phụ thuộc entity nội bộ. |
| Compatibility test | Phiên bản ứng dụng chuyển tiếp vẫn hoạt động | Kiểm tra ứng dụng cũ với schema sau expand và ứng dụng mới trong giai đoạn chuyển tiếp. |

H2 hoặc database giả lập có thể hữu ích cho kiểm thử nhanh, nhưng không bảo đảm tương thích hoàn toàn với PostgreSQL, MySQL hoặc engine production. Với migration phụ thuộc cú pháp, kiểu dữ liệu, index hoặc locking riêng của engine, nên kiểm thử trên đúng hệ quản trị hoặc một môi trường tương thích đủ gần.

Không nên chỉ kiểm tra rằng migration chạy không lỗi. Cần xác nhận dữ liệu sau migration, constraint, index, thời gian thực hiện và hành vi truy vấn quan trọng. Với bảng lớn, dùng lượng dữ liệu đại diện để ước lượng thời gian và tải; database rỗng không thể bộc lộ mọi vấn đề khóa hoặc backfill.

## 11. Các dấu hiệu ranh giới dữ liệu đang bị phá vỡ

- Controller hoặc service nghiệp vụ tự inject `JdbcTemplate`, `EntityManager` hay `DataSource` để truy vấn bảng nội bộ.
- Nhiều module dùng chung entity JPA hoặc phụ thuộc vào tên bảng/cột của nhau.
- Một thay đổi schema buộc sửa nhiều controller hoặc service không sở hữu dữ liệu.
- Migration được chạy thủ công ở production nhưng không có lịch sử tương ứng trong repository.
- Tài khoản runtime có quyền tạo/xóa bảng dù ứng dụng không cần.
- Migration xóa hoặc đổi tên cột ngay trong một lần phát hành khi các phiên bản ứng dụng có thể còn chạy đồng thời.
- Kiểm thử chỉ dựng database rỗng, không nâng cấp từ phiên bản schema trước hoặc không xác minh dữ liệu sau backfill.

Khi gặp các dấu hiệu này, hãy xác định chủ sở hữu dữ liệu và nơi nên đặt thao tác lưu trữ, sau đó công bố hợp đồng phù hợp. Nếu cần thay schema, lập kế hoạch migration theo thời gian sống của các consumer thay vì chỉ sửa SQL và triển khai một lần.

## 12. Tự rà soát trước khi thay đổi schema

Trước khi merge hoặc phát hành một migration, hãy trả lời:

1. Migration thay đổi đối tượng nào và module/dịch vụ nào sở hữu chúng?
2. Dữ liệu hiện tại có đáp ứng constraint hoặc kiểu dữ liệu mới không? Nếu chưa, quy tắc chuyển đổi là gì?
3. Ứng dụng cũ và mới có thể cùng chạy trong thời gian triển khai không?
4. Có thể chia thay đổi thành expand, migrate và contract không?
5. Migration có thể gây khóa, transaction dài, tăng dung lượng hoặc ảnh hưởng truy vấn nào?
6. Có thể tiếp tục hoặc khôi phục nếu backfill/migration dừng giữa chừng không?
7. Tài khoản chạy migration và tài khoản runtime có quyền tối thiểu phù hợp không?
8. Các tầng và module khác có đang truy cập trực tiếp schema nội bộ không?
9. Đã kiểm thử nâng cấp từ phiên bản trước, cài mới và dữ liệu đại diện chưa?
10. Có chỉ số và điều kiện xác nhận thành công sau triển khai không?

## Kết luận

Quản lý schema bằng migration có phiên bản giúp thay đổi cơ sở dữ liệu có lịch sử, có thể review và đồng bộ giữa các môi trường. Những thay đổi có nguy cơ phá vỡ tương thích nên được triển khai theo giai đoạn, chuyển dữ liệu có kiểm soát và chỉ loại bỏ cấu trúc cũ sau khi consumer đã chuyển. Đồng thời, tầng truy cập dữ liệu cần giữ quyền sở hữu truy vấn, mapping và cơ chế lưu trữ; các tầng khác sử dụng hợp đồng được công bố thay vì truy cập tùy ý vào bảng nội bộ. Kết hợp migration, quyền database, cấu trúc module và kiểm thử kiến trúc giúp schema phát triển mà không làm ranh giới của ứng dụng mất tác dụng.
