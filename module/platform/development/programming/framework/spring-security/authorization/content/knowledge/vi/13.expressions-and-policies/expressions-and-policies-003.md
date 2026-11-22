# Phép toán logic, độ ưu tiên và tính dễ đọc của biểu thức trong Spring Security

## 1. Vì sao thứ tự logic là vấn đề bảo mật?

Trong Spring Security, các chính sách như `@PreAuthorize` và `@PostAuthorize` có thể dùng Spring Expression Language (SpEL) để kết hợp các điều kiện về vai trò, quyền thao tác, danh tính người dùng, tenant và tài nguyên. Chỉ cần thiếu một cặp ngoặc, biểu thức có thể cấp quyền cho người đáng lẽ phải bị từ chối.

Ví dụ yêu cầu nghiệp vụ: **người dùng phải thuộc cùng tenant với tài liệu VÀ phải là ADMIN HOẶC có quyền đọc tài liệu**. Có ba điều kiện:

- `A`: người dùng có vai trò ADMIN.
- `B`: người dùng có authority `document:read`.
- `C`: người dùng và tài liệu thuộc cùng tenant.

Chính sách mong muốn là `(A or B) and C`. Nhưng biểu thức `A or B and C` được hiểu là `A or (B and C)` vì `and` có độ ưu tiên cao hơn `or`. Vì thế, ADMIN có thể vượt qua điều kiện tenant (`A = true` làm cả biểu thức đúng), dù nghiệp vụ yêu cầu **mọi người** đều ở đúng tenant.

Mục tiêu bài học: nhận diện toán tử logic trong SpEL, đọc đúng độ ưu tiên, chủ động nhóm điều kiện bằng ngoặc, viết chính sách dễ kiểm chứng và tránh lỗi cấp quyền quá rộng.

## 2. Ngữ cảnh: biểu thức SpEL trong bảo mật mức phương thức

Spring Security sử dụng SpEL để diễn đạt quyết định cho các annotation như:

- `@PreAuthorize("...")`: đánh giá trước khi gọi phương thức, thường dùng để từ chối hành động sớm.
- `@PostAuthorize("...")`: đánh giá sau khi phương thức trả về, có thể tham chiếu kết quả qua `returnObject`. Không dùng cách này để ngăn tác dụng phụ đã xảy ra trong phương thức.
- `@PreFilter` và `@PostFilter`: lọc các phần tử đầu vào/đầu ra, cũng sử dụng biểu thức nhưng phục vụ bài toán lọc tập hợp.

Với ứng dụng Spring Boot dùng Spring Security, cần bật method security bằng cấu hình sau (đây là thành phần cấu hình trong ứng dụng, không phải một chương trình Java chạy độc lập):

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Chỉ thêm dependency Spring Security chưa mặc nhiên kích hoạt method security. Khi phương thức của Spring bean được gọi qua interceptor/proxy phù hợp, Spring Security đánh giá biểu thức trong ngữ cảnh có `authentication`, `principal`, những hàm như `hasAuthority(...)`, `hasRole(...)` và các tham số phương thức dạng `#parameterName`.

Ví dụ:

```java
@PreAuthorize("hasAuthority('document:read') and #documentId != null")
public Document findOne(Long documentId) {
    // Tải tài liệu bằng repository; chỉ là ví dụ từng phần.
}
```

Ý nghĩa: cả điều kiện có quyền đọc lẫn kiểm tra ID khác `null` phải đúng. Kiểm tra ID này **chưa** đủ để phân quyền đến tài liệu cụ thể; phần sau sẽ dùng một bean chính sách đáng tin cậy cho việc đó.

## 3. Ba phép toán logic cốt lõi

| Phép toán | Cú pháp SpEL | Kết quả đúng khi | Gợi ý đọc |
| --- | --- | --- | --- |
| AND | `and` hoặc `&&` | Tất cả các toán hạng đều đúng | "và" — phải thỏa mọi điều kiện |
| OR | `or` hoặc `||` | Có ít nhất một toán hạng đúng | "hoặc" — có thể thỏa một trong các nhánh |
| NOT | `not` hoặc `!` | Toán hạng sai | "không" — đảo kết quả logic |

Các dạng chữ `and`, `or`, `not` không phân biệt chữ hoa/thường trong SpEL. Vì `@PreAuthorize` nhận một chuỗi Java, có thể chọn dạng chữ để dễ đọc chính sách hoặc dạng ký hiệu quen thuộc với lập trình viên. **Nên thống nhất một phong cách trong cùng mã nguồn.**

Các ví dụ hợp lệ:

```java
@PreAuthorize("hasAuthority('document:read') and isAuthenticated()")
@PreAuthorize("hasRole('ADMIN') or hasAuthority('document:read')")
@PreAuthorize("not hasAuthority('account:suspended')")
@PreAuthorize("hasAuthority('document:read') && !hasAuthority('account:suspended')")
```

Bốn annotation trên là **bốn ví dụ riêng** cho các phương thức khác nhau; không gắn bốn `@PreAuthorize` đồng thời vào một phương thức.

Điểm cần nhớ: `hasRole('ADMIN')` thường kiểm tra authority với tiền tố `ROLE_` (tùy cấu hình prefix), còn `hasAuthority('document:read')` so khớp trực tiếp chuỗi authority. Đừng dùng lẫn role và authority mà chưa hiểu dữ liệu quyền thực tế.

## 4. Độ ưu tiên: NOT → AND → OR

Khi một biểu thức kết hợp những toán tử logic thông thường, thứ tự ưu tiên từ cao xuống thấp là:

1. **Ngoặc `(...)`** được nhóm để thể hiện ý đồ, và quyết định cấu trúc đánh giá.
2. **Phủ định `not` / `!`** áp dụng cho toán hạng hoặc nhóm tương ứng.
3. **Phép hội `and` / `&&`** kết hợp các điều kiện.
4. **Phép tuyển `or` / `||`** kết hợp các nhánh.

Các so sánh như `==`, `!=`, `>`, `>=`, lời gọi hàm và truy cập thuộc tính thường là phần tạo ra giá trị boolean để ghép bằng `and/or`. Khi trộn nhiều loại toán tử, **đặt ngoặc quanh các kiểm tra cần làm rõ**, thay vì yêu cầu người đọc nhớ một bảng độ ưu tiên dài hơn.

Ví dụ:

```text
A or B and C        ≡ A or (B and C)
not A and B         ≡ (not A) and B
not (A and B)       ≠ (not A) and B
(A or B) and C      ≠ A or (B and C)
```

Dấu `≡` là tương đương logic; `≠` nói hai biểu thức có thể cho kết quả khác nhau. Với `A = true, B = false, C = false`:

- `A or B and C` → `true or (false and false)` → `true`.
- `(A or B) and C` → `(true or false) and false` → `false`.

Đây là kiểu lỗi nghiêm trọng: **quyền ADMIN làm bỏ qua điều kiện bắt buộc cùng tenant** ở cách viết đầu.

### Bảng kiểm tra nhóm điều kiện

| A: ADMIN | B: document:read | C: cùng tenant | `A or B and C` | `(A or B) and C` |
| --- | --- | --- | --- | --- |
| true | false | false | **true** | **false** |
| true | false | true | true | true |
| false | true | true | true | true |
| false | true | false | false | false |
| false | false | true | false | false |
| false | false | false | false | false |

Trường hợp đầu tiên đủ để xác định biểu thức không có ngoặc **không tương đương** với yêu cầu nghiệp vụ.

## 5. Dùng ngoặc để biểu đạt chính sách trước khi tối ưu cú pháp

Giả sử trong ứng dụng có bean `documentPolicy` với phương thức `sameTenant(documentId)` xác minh tenant từ thông tin đã được xác thực ở server và dữ liệu tài liệu trong database.

**Dễ mắc lỗi:**

```java
@PreAuthorize(
    "hasRole('ADMIN') or hasAuthority('document:read') and " +
    "@documentPolicy.sameTenant(#documentId)"
)
public Document read(Long documentId) {
    // ...
}
```

Theo độ ưu tiên, phần tenant chỉ ràng buộc nhánh `document:read`. ADMIN đi qua nhánh đầu mà không cần kiểm tra tenant.

**Đúng với yêu cầu mọi người phải cùng tenant:**

```java
@PreAuthorize(
    "(hasRole('ADMIN') or hasAuthority('document:read')) and " +
    "@documentPolicy.sameTenant(#documentId)"
)
public Document read(Long documentId) {
    // ...
}
```

Mặc dù có thể suy ra độ ưu tiên, ngoặc ở đây còn có giá trị như một phần tài liệu: hai nhánh quyền thao tác được nhóm lại, sau đó **nhóm quyền** phải thỏa điều kiện tenant.

Nếu chính sách thực sự cho phép ADMIN xuyên tenant, đó phải là một **quyết định nghiệp vụ có chủ đích**, ví dụ chính sách riêng `hasAuthority('platform:cross-tenant-read')` với kiểm toán và kiểm tra đầy đủ. Không ngầm coi việc thiếu ngoặc là chính sách cho phép vượt tenant.

### Phủ định cả nhóm hay một nhánh?

Hai biểu thức sau khác nhau:

```text
not (A or B)   = (not A) and (not B)
(not A) or B   = từ chối A nhưng vẫn chấp nhận B
```

Nếu cần từ chối khi người dùng có **bất kỳ** authority cấm nào, viết:

```java
@PreAuthorize(
    "not (hasAuthority('account:suspended') or " +
    "hasAuthority('account:blocked'))"
)
```

Đừng thay bằng:

```java
@PreAuthorize(
    "not hasAuthority('account:suspended') or " +
    "hasAuthority('account:blocked')"
)
```

Biểu thức sai sẽ chấp nhận một tài khoản vừa có `account:blocked` nhưng không có `account:suspended`. Ngoặc sau `not` xác định rõ **phạm vi bị phủ định**.

## 6. Short-circuit: ngắn mạch ảnh hưởng thứ tự đánh giá

Các toán tử logic `and` và `or` của SpEL đánh giá theo cơ chế ngắn mạch đối với các toán hạng boolean:

- `A and B`: nếu `A` đã `false`, không cần đánh giá `B`.
- `A or B`: nếu `A` đã `true`, không cần đánh giá `B`.

Điều này có thể giúp tránh lỗi khi điều kiện bên phải cần đối tượng không null:

```java
@PreAuthorize(
    "#document != null and " +
    "#document.ownerUsername == authentication.name"
)
public void update(Document document) {
    // ...
}
```

Nếu `#document` là `null` thì vế phải không được truy cập, tránh lỗi đọc `ownerUsername` từ đối tượng null. Ở ứng dụng thực, **đừng tin thuộc tính owner do client tự gửi**: vẫn phải tra quyền ở nguồn dữ liệu tin cậy để tránh giả mạo dữ liệu.

Đảo thứ tự thành:

```java
@PreAuthorize(
    "#document.ownerUsername == authentication.name and " +
    "#document != null"
)
```

không còn an toàn khi `document` có thể null: chương trình cố đọc property trước khi kiểm tra.

Ngắn mạch giúp giảm việc tính toán thừa, nhưng **không nên phụ thuộc vào side effect** của một hàm trong SpEL (ghi log, tăng counter, thay đổi dữ liệu...) để quyết định đúng/sai. Các hàm đánh giá quyền nên thuần về mục đích, không sửa trạng thái; một hàm bên phải có thể không được gọi.

## 7. So sánh, null và điều kiện nhận từ client

Trong biểu thức truy cập, các điều kiện về dữ liệu thường ghép với điều kiện quyền:

```java
@PreAuthorize(
    "hasAuthority('order:read') and " +
    "#orderId != null and #orderId > 0"
)
```

Ví dụ này kiểm tra quyền thao tác và kiểu giá trị ID hợp lệ ở mức đơn giản. Nó **không** chứng minh người dùng được phép đọc đơn hàng có ID đó.

Tránh suy luận `#ownerUsername == authentication.name` là đủ an toàn nếu `ownerUsername` được truyền từ request: người gọi có thể cung cấp bất kỳ giá trị nào. Quyết định sở hữu/cùng tenant phải xác minh bằng dữ liệu do server kiểm soát.

Để ưu tiên độ rõ ràng khi so sánh và điều kiện logic:

```java
@PreAuthorize(
    "hasAuthority('order:read') and " +
    "(#orderId != null) and " +
    "@orderPolicy.canRead(authentication, #orderId)"
)
```

Trong đó `orderPolicy.canRead(...)` nên trả về `false` khi thiếu thông tin hợp lệ và đối chiếu order với danh tính, tenant, ACL đáng tin cậy. Đặc biệt, cần định nghĩa rõ điều kiện tenant có được phép bỏ qua hay không; tránh tình trạng một nhánh `or` vô tình bỏ qua ràng buộc chung.

**Không dùng toán tử quan hệ với `null` như một mẹo so sánh số:** SpEL có quy tắc so sánh `null` riêng, khác với ý tưởng "null là 0". Thay vào đó, kiểm tra null và ranh giới giá trị tường minh.

## 8. Viết biểu thức dễ đọc ở nhiều mức độ phức tạp

### Mức 1: một yêu cầu quyền đơn giản

```java
@PreAuthorize("hasAuthority('invoice:read')")
public Invoice loadInvoice(Long id) {
    // ...
}
```

Khi chính sách chỉ cần một authority, biểu thức ngắn là lựa chọn tốt. Nếu hai authority là các lựa chọn thay thế thực sự, `hasAnyAuthority(...)` rõ ràng hơn chuỗi `or` dài:

```java
@PreAuthorize("hasAnyAuthority('invoice:read', 'invoice:admin')")
```

### Mức 2: kết hợp một nhóm lựa chọn và một điều kiện bắt buộc

```java
@PreAuthorize(
    "(hasAuthority('invoice:read') or hasAuthority('invoice:admin')) " +
    "and @invoicePolicy.sameTenant(#invoiceId)"
)
```

Có thể dùng ngoặc ngay cả khi người viết đã hiểu độ ưu tiên: người review sẽ thấy nhóm nào là `OR` và điều kiện nào áp dụng cho mọi nhánh.

### Mức 3: nhiều quy tắc, chuyển sang một bean chính sách

Biểu thức quá dài dễ che mất lỗ hổng khi thay đổi một nhánh. Nên trích riêng logic nghiệp vụ:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public Document read(@P("documentId") Long documentId) {
        // Tải tài liệu bằng repository được tiêm vào service.
        // Phần thân minh họa, chưa phải triển khai độc lập.
        throw new UnsupportedOperationException("Illustrative code");
    }
}
```

Đoạn trên minh họa cách tham số `#documentId` được đặt tên rõ bằng `@P` và cách gọi bean `@documentPolicy` qua SpEL. Đây là **một phần trong ứng dụng Spring**, cần có lớp `Document`, bean `documentPolicy` và repository của dự án; không phải một lớp độc lập để chạy.

`DocumentPolicy.canRead(authentication, documentId)` cần đối chiếu quyền cấp cho người dùng, tenant hiện tại và sở hữu/chia sẻ/ACL trên dữ liệu thật. Nếu việc kiểm tra này phức tạp, đưa vào Java thông thường sẽ giúp đặt tên điều kiện, viết unit test và tối ưu truy vấn thuận tiện hơn. **Tên hàm nên giải thích chính sách**, chẳng hạn `canRead`, `canModify`, `sameTenant`; tránh `check1` hoặc `isOk`.

Ngoài ra, có thể cấp cho tài khoản quản trị authority đã bao hàm quyền đọc theo mô hình quyền hoặc role hierarchy được thiết kế cẩn thận, để biểu thức chỉ còn `hasAuthority('document:read')`. Tuy nhiên role hierarchy không được tự ý bỏ qua các ràng buộc theo từng tài nguyên hay tenant.

## 9. Ví dụ Java 17 chạy độc lập: kiểm tra đúng/sai của dấu ngoặc

Đây là chương trình **Java thuần mô phỏng logic boolean**, không cần Spring và không thực thi SpEL. Vì ba toán tử tương ứng trong ví dụ có cùng ý nghĩa boolean như `!`, `&&` và `||` của Java, chương trình giúp thấy rõ tác động của việc thiếu ngoặc.

Lưu mã dưới tên `LogicPrecedenceDemo.java`:

```java
public class LogicPrecedenceDemo {

    private static boolean implicit(
            boolean admin, boolean canRead, boolean sameTenant) {
        return admin || canRead && sameTenant;
    }

    private static boolean grouped(
            boolean admin, boolean canRead, boolean sameTenant) {
        return (admin || canRead) && sameTenant;
    }

    private static void check(
            String scenario,
            boolean admin, boolean canRead, boolean sameTenant) {
        System.out.printf(
            "%s: implicit=%s, grouped=%s%n",
            scenario,
            implicit(admin, canRead, sameTenant),
            grouped(admin, canRead, sameTenant)
        );
    }

    public static void main(String[] args) {
        check("Admin outside tenant", true, false, false);
        check("Reader inside tenant", false, true, true);
        check("Reader outside tenant", false, true, false);
        check("No permission", false, false, true);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LogicPrecedenceDemo.java
java LogicPrecedenceDemo
```

Kết quả tiêu chuẩn (stdout):

```text
Admin outside tenant: implicit=true, grouped=false
Reader inside tenant: implicit=true, grouped=true
Reader outside tenant: implicit=false, grouped=false
No permission: implicit=false, grouped=false
```

Dòng đầu cho thấy cùng ba boolean, chỉ khác cách nhóm, kết quả phân quyền đã thay đổi. Trong ứng dụng Spring, cần **kiểm thử annotation thật** nữa, vì ví dụ thuần Java không kiểm tra interceptor, cách gọi bean, dữ liệu `Authentication` hay việc tra quyền tại database.

## 10. Kiểm thử chính sách như một bảng chân trị

Với bất kỳ biểu thức gồm hai hoặc ba điều kiện, cách nhanh nhất để phát hiện lỗi nhóm là lập bảng chân trị. Gọi:

- `P` = có authority đọc;
- `T` = cùng tenant đã xác minh;
- `S` = tài nguyên đang được chia sẻ với người dùng.

Yêu cầu: `P and T and S` cho một quyền đọc tài nguyên chia sẻ nghiêm ngặt. Nếu quy tắc là `P and T and (S or owner)`, phải viết ngoặc đúng quanh hai cách hợp lệ để truy cập tài nguyên. Không để `owner` xuất hiện ở một nhánh `or` ngoài cả `P` hoặc `T` trừ khi nghiệp vụ thực sự cho phép điều đó.

Khi có Spring Security Test, các integration test nên gọi service **qua Spring bean/proxy**, dùng những danh tính với quyền khác nhau và dữ liệu thực hoặc repository giả lập có kiểm soát. Các tình huống tối thiểu:

| Tình huống | Quyền thao tác | Cùng tenant | Quyền trên tài nguyên | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Người được phép | Có | Có | Có | Cho phép |
| Thiếu authority | Không | Có | Có | Từ chối |
| Khác tenant | Có | Không | Có | Từ chối |
| Không sở hữu/không được chia sẻ | Có | Có | Không | Từ chối |
| ADMIN nhưng khác tenant (nếu tenant bắt buộc) | ADMIN | Không | Tùy nghiệp vụ | Từ chối |
| Tham số ID null/không tồn tại | Có | Không xác định | Không | Từ chối |

Ví dụ `@WithMockUser(authorities = "document:read")` có thể tạo danh tính giả trong bài test; `@WithMockUser(roles = "ADMIN")` tạo role mặc định tương ứng với `ROLE_ADMIN`. Nhưng test vẫn cần thực sự kiểm tra đường đi phân quyền, không chỉ gọi một hàm Java chưa qua proxy.

Nên có kiểm thử **đối nghịch** cho các nhóm ngoặc:
 
- `hasRole('ADMIN') or P and T` so với `(hasRole('ADMIN') or P) and T` khi `ADMIN = true` và `T = false`.
- `not (blocked or suspended)` so với `not blocked or suspended` khi `blocked = false`, `suspended = true`.
- `P and (#resource != null) and check(resource)` khi resource là null để phát hiện truy cập property sai thứ tự.
- Điều kiện tại method có áp dụng khi gọi qua bean khác hay không; gọi nội bộ từ `this.method()` có thể bỏ qua Spring proxy.
- Không lộ thông tin hay thực hiện tác dụng phụ không được phép trong thân phương thức trước khi `@PostAuthorize` chạy.

## 11. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Viết `A or B and C` trong khi muốn `(A or B) and C` | Nhánh `A` bỏ qua `C` | Viết ngoặc theo quy tắc nghiệp vụ trước |
| Đảo `not (A or B)` thành `not A or B` | Phủ định sai phạm vi, có thể cho phép đối tượng bị cấm | Đặt ngoặc quanh toàn bộ nhóm cần phủ định |
| Gộp mọi điều kiện bằng một chuỗi rất dài | Khó review, khó phát hiện nhánh cho phép quá rộng | Dùng `hasAnyAuthority` hoặc bean `@policy` có tên rõ |
| Dùng `hasRole('ADMIN')` nhưng dữ liệu chỉ có `ADMIN`, hoặc dùng `hasAuthority('ADMIN')` khi thực tế chỉ có `ROLE_ADMIN` | Quyền được đánh giá khác kỳ vọng | Kiểm tra authority thực và cấu hình role prefix |
| Đặt kiểm tra null sau khi truy cập property | Có thể gây exception trước khi đến điều kiện null | Đặt kiểm tra trước và dùng `and` có ngắn mạch |
| Tin dữ liệu từ request để kết luận owner/tenant | Dễ bị giả mạo để truy cập chéo | Lấy identity/tenant từ ngữ cảnh đáng tin và tra DB/ACL |
| Viết kiểm tra chỉ ở annotation sau khi phương thức đã xử lý | Tác dụng phụ hoặc dữ liệu trung gian đã xuất hiện | Kiểm tra trước, bảo vệ truy vấn và giao dịch |
| Không test trường hợp một nhánh `OR` đúng nhưng điều kiện bắt buộc sai | Không phát hiện bypass khi nhóm thiếu ngoặc | Dùng bảng chân trị và test negative case |
| Dùng tên biến `A`/`B` trong chính sách thực tế | Người đọc không biết ý nghĩa nghiệp vụ | Tách thành hàm `canRead`, `sameTenant`, `isOwner` |

**Một lưu ý về annotation:** không thể khai báo lặp nhiều `@PreAuthorize` trên cùng một phương thức để biểu thị các điều kiện khác nhau. Nếu trên phương thức có nhiều annotation bảo mật **khác loại**, Spring Security đánh giá từng interceptor; mọi kiểm tra liên quan cần vượt qua, về mặt tổng thể tương tự `AND`. Đừng suy đoán thứ tự chạy để tạo ra một quan hệ `OR` ngầm; khi cần lựa chọn, viết `or` rõ ràng trong một chính sách hoặc dùng thành phần authorization thích hợp.

## 12. Checklist khi review biểu thức phân quyền

Trước khi merge một quy tắc SpEL, tự kiểm tra:

1. **Viết yêu cầu bằng lời:** những điều kiện nào bắt buộc cho tất cả, những điều kiện nào là phương án thay thế?
2. **Nhóm bằng ngoặc:** tạo `(A or B) and C` theo lời mô tả; không tin vào thói quen đọc từ trái sang phải.
3. **Kiểm tra phủ định:** `not` áp dụng lên một điều kiện hay cả nhóm điều kiện?
4. **Phân biệt role/authority:** có tiền tố `ROLE_` hay custom prefix không?
5. **Kiểm tra nguồn dữ liệu:** identity, tenant, owner, ACL có đến từ server/database đáng tin cậy không?
6. **Xem đường đánh giá:** kiểm tra null và điều kiện đơn giản trước khi truy cập sâu; tránh hàm có tác dụng phụ và kiểm tra tốn kém lặp lại.
7. **Đặt tên dễ hiểu:** nếu biểu thức dài, chuyển logic sang bean Java và viết test độc lập.
8. **Thử trường hợp phủ định:** một nhánh `OR` đúng nhưng yêu cầu bắt buộc sai; ADMIN khác tenant; thiếu quyền; ID null.
9. **Thử qua Spring proxy:** bảo đảm annotation thực sự chạy tại điểm gọi service.
10. **Giữ chính sách dễ kiểm toán:** chú thích bằng ý định nghiệp vụ nếu cần; một biểu thức ngắn, rõ và được kiểm thử thường tốt hơn biểu thức "khéo" nhưng khó đọc.

### Tự luyện

Xét yêu cầu: "*Chỉ tài khoản đang hoạt động được xuất báo cáo; tài khoản đó phải là quản trị viên **hoặc** có quyền xuất báo cáo; mọi trường hợp đều phải thuộc đúng tenant.*"

Đặt `A = active`, `R = admin`, `E = export permission`, `T = same tenant`.

- Cách diễn đạt đúng: `A and (R or E) and T`.
- Cách dễ lỗi: `A and R or E and T` (vì tương đương `(A and R) or (E and T)`).
- Phản ví dụ: `A = false, R = false, E = true, T = true`. Cách lỗi trả `true` cho tài khoản ngừng hoạt động, còn cách đúng trả `false`.

Ánh xạ sang SpEL minh họa:

```java
@PreAuthorize(
    "@accountPolicy.isActive(authentication) and " +
    "(hasRole('ADMIN') or hasAuthority('report:export')) and " +
    "@tenantPolicy.canAccess(authentication, #tenantId)"
)
```

Cả `accountPolicy` và `tenantPolicy` phải dùng trạng thái tài khoản, tenant membership và quyền được xác minh ở server. `tenantId` có thể là đầu vào yêu cầu nhưng **không** phải chứng cứ rằng người gọi có quyền trên tenant đó.

## Tài liệu chính thức

- [Spring Framework — SpEL: Operators](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html): cú pháp `and`, `or`, `not`, toán tử so sánh và cách viết tương đương.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): cú pháp biểu thức, cách dùng khoảng trắng và cấu trúc ngôn ngữ.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, biểu thức authority/role, các bean chính sách và cách kiểm thử method authorization.
