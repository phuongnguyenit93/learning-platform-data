# Kiểm thử đọc phiên được tạo bởi phiên bản ứng dụng cũ

Session của Spring Session thường tồn tại lâu hơn một request và có thể tồn tại qua nhiều lần triển khai ứng dụng. Khi một phiên bản mới được phát hành, repository Redis hoặc JDBC vẫn có thể chứa session được ghi bởi phiên bản trước. Instance mới phải đọc được dữ liệu đó nếu người dùng chưa đăng xuất và session chưa hết hạn.

Vấn đề này không chỉ nằm ở việc Java có thể tuần tự hóa một lớp hay không. Session có thể chứa nhiều loại thuộc tính: DTO của ứng dụng, principal và Authentication của Spring Security, collection, enum, dữ liệu do thư viện tạo ra hoặc các kiểu đã thay đổi giữa hai bản phát hành. Nếu serializer, tên lớp, cấu trúc trường hoặc dependency thay đổi, request đầu tiên sau khi triển khai có thể gặp lỗi deserialize.

Bài này trình bày cách kiểm thử khả năng đọc session cũ trước khi phát hành phiên bản mới. Trọng tâm là tạo dữ liệu kiểm thử từ đúng phiên bản cũ, kiểm tra serializer và cấu trúc thuộc tính, thử nghiệm rolling deployment, xác định chính sách tương thích và xử lý session không thể đọc một cách an toàn.

## 1. Vì sao session cũ có thể không đọc được?

Session được lưu trong repository dưới dạng metadata và các thuộc tính đã được tuần tự hóa. Metadata như ID, thời điểm tạo, lần truy cập gần nhất và thời gian không hoạt động do Spring Session quản lý. Các thuộc tính ứng dụng có thể chứa object Java hoặc dữ liệu được chuyển đổi theo serializer đang cấu hình.

Một phiên bản mới có thể không đọc được session cũ vì:

- Lớp của thuộc tính đã đổi package hoặc tên đầy đủ.
- Kiểu dữ liệu của một trường đã đổi, chẳng hạn String thành UUID hoặc int thành một kiểu khác.
- Cấu trúc kế thừa, tên lớp hoặc serialVersionUID không còn tương thích với Java serialization.
- Enum bị xóa hoặc đổi tên giá trị mà session cũ đang lưu.
- Một lớp principal hoặc Authentication của Spring Security thay đổi giữa các phiên bản dependency.
- Serializer được đổi, ví dụ từ Java serialization sang JSON, trong khi dữ liệu cũ vẫn còn ở định dạng trước.
- Cấu hình Jackson hoặc metadata kiểu thay đổi khiến JSON cũ không còn được ánh xạ về đúng kiểu.
- Phiên bản mới không còn class hoặc thư viện cần thiết để giải mã thuộc tính cũ.
- Một instance cũ và một instance mới cùng đọc/ghi session trong giai đoạn rolling deployment nhưng không hiểu cùng một định dạng.

Ví dụ, phiên bản 1 lưu thuộc tính:

~~~java
public class CheckoutDraft implements Serializable {
    private String cartId;
    private String shippingCode;
}
~~~

Phiên bản 2 đổi shippingCode thành một kiểu khác:

~~~java
public class CheckoutDraft implements Serializable {
    private String cartId;
    private ShippingMethod shippingCode;
}
~~~

Nếu session cũ chứa chuỗi như "EXPRESS", phiên bản mới có thể không chuyển đổi được giá trị đó thành ShippingMethod, tùy serializer và cách class được tuần tự hóa. Việc ứng dụng biên dịch thành công không chứng minh session đã lưu trước đó có thể đọc được.

## 2. Phân biệt tương thích của repository, serializer và lớp thuộc tính

Khi điều tra lỗi, hãy chia vấn đề thành các lớp riêng:

| Lớp | Nội dung cần tương thích | Ví dụ lỗi |
|---|---|---|
| Repository | Cùng cách tìm và lưu session, schema/keyspace và namespace phù hợp | Phiên bản mới tìm trong namespace Redis khác hoặc schema JDBC không khớp |
| Serializer | Định dạng byte hoặc JSON dùng để mã hóa/giải mã thuộc tính | Dữ liệu Java serialization bị đọc bằng JSON serializer |
| Kiểu dữ liệu | Class, field, enum, collection và quan hệ giữa các lớp | Không tìm thấy class cũ hoặc đổi kiểu field |
| Framework/security | Các kiểu do Spring Security hoặc thư viện lưu trong session | SecurityContext hoặc principal không deserialize được |
| Chính sách phiên | TTL, cookie, session ID và quy tắc xác thực | Cookie còn nhưng session đã hết hạn hoặc bị thu hồi |

Một lỗi đọc session có thể xuất hiện ở bất kỳ lớp nào. Không nên chỉ kiểm tra repository kết nối được Redis/JDBC rồi kết luận tương thích. Repository có thể tìm thấy dữ liệu nhưng serializer thất bại khi giải mã một thuộc tính.

Ngược lại, một session ID không còn tồn tại thường được repository xử lý như không tìm thấy session. Đây khác với lỗi deserialize: key có thể vẫn tồn tại, nhưng nội dung không thể được chuyển thành object hiện tại.

## 3. Xác định dữ liệu session thực sự cần giữ qua lần triển khai

Trước khi viết kiểm thử, hãy lập danh sách các thuộc tính có thể tồn tại trong session đang hoạt động:

| Thuộc tính | Nguồn | Mức độ quan trọng khi nâng cấp | Hành vi nếu không đọc được |
|---|---|---|---|
| SPRING_SECURITY_CONTEXT | Spring Security | Rất cao đối với phiên đăng nhập | Yêu cầu xác thực lại; không bỏ qua lỗi rồi cấp quyền |
| app.activeCartId | Ứng dụng | Có thể khôi phục từ dữ liệu nghiệp vụ | Xóa tham chiếu không hợp lệ hoặc tải lại giỏ hàng |
| app.checkoutDraft | Ứng dụng | Tùy luồng thanh toán | Chuyển đổi định dạng hoặc yêu cầu tiếp tục lại bước |
| app.uiLocale | Ứng dụng | Thấp | Dùng locale mặc định |
| app.recentItems | Ứng dụng | Thường thấp | Có thể khởi tạo lại |
| Thuộc tính do thư viện thêm | Dependency | Phụ thuộc thư viện và phiên bản | Kiểm thử với đúng phiên bản framework |

Không nên lưu toàn bộ entity JPA, object chứa proxy hoặc đồ thị object lớn vào session. Những object này làm tăng rủi ro tương thích khi schema, mapping hoặc dependency thay đổi. Session nên giữ các giá trị nhỏ và ổn định như ID, mã trạng thái, lựa chọn giao diện hoặc DTO được thiết kế có chủ đích.

Đối với dữ liệu nghiệp vụ cần tồn tại lâu hơn vòng đời triển khai, hãy lưu trong database nghiệp vụ và chỉ giữ ID tham chiếu trong session. Điều này giảm lượng dữ liệu phải chuyển đổi khi nâng cấp.

## 4. Java serialization và thay đổi lớp

Nếu serializer dùng Java serialization, khả năng đọc dữ liệu cũ phụ thuộc class được nạp ở phiên bản mới và các quy tắc tương thích của Java serialization.

### serialVersionUID

Serializable class có thể khai báo serialVersionUID rõ ràng:

~~~java
public class CheckoutDraft implements Serializable {

    private static final long serialVersionUID = 1L;

    private String cartId;
    private String shippingCode;
}
~~~

Khai báo serialVersionUID ổn định giúp tránh việc Java tự tính UID mới chỉ vì một số thay đổi cấu trúc. Tuy nhiên, giữ nguyên UID không bảo đảm mọi thay đổi đều tương thích. Nếu thay kiểu field, thay cấu trúc lớp hoặc thay ý nghĩa dữ liệu, việc deserialize vẫn có thể lỗi hoặc tạo object không còn đúng về nghiệp vụ.

Một số nguyên tắc:

- Thêm field mới có thể tương thích; field mới thường nhận giá trị mặc định khi đọc stream cũ nếu không có cơ chế chuyển đổi riêng.
- Xóa field thường khiến dữ liệu cũ của field đó bị bỏ qua, nhưng ứng dụng phải chấp nhận việc mất thông tin đó.
- Đổi kiểu field có thể gây InvalidClassException hoặc lỗi chuyển đổi.
- Đổi tên class hoặc package làm tên lớp trong stream không còn khớp với class mới.
- Thay đổi class hierarchy hoặc enum cần được kiểm thử với dữ liệu thật từ bản cũ.
- Không thay serialVersionUID một cách tùy tiện nếu muốn đọc stream cũ; cũng không giữ UID một cách máy móc khi cấu trúc mới không còn tương thích.

Không dùng việc compile thành công làm tiêu chí duy nhất. Hãy deserialize fixture được tạo bởi artifact cũ trong test chạy với classpath của phiên bản mới.

### readObject và readResolve

Java serialization có các hook như readObject hoặc readResolve để kiểm soát quá trình đọc object. Chúng có thể hỗ trợ migration ở mức class, nhưng cần thận trọng:

- Hook phải xử lý dữ liệu thiếu hoặc giá trị mặc định từ stream cũ.
- Không thực hiện truy vấn mạng hoặc truy cập database trong readObject.
- Không phụ thuộc bean Spring trong quá trình deserialize.
- Kiểm tra bất biến object sau khi đọc.
- Không dùng hook để âm thầm bỏ qua dữ liệu không hợp lệ rồi tạo object có trạng thái bảo mật sai.

Nếu migration cần gọi service hoặc tra cứu dữ liệu nghiệp vụ, hãy thực hiện sau khi deserialize ở tầng ứng dụng, nơi có dependency và xử lý lỗi rõ ràng.

## 5. JSON serializer và schema evolution

Một số ứng dụng chọn JSON để dễ quan sát, hỗ trợ nhiều ngôn ngữ hoặc giảm phụ thuộc vào Java class name. JSON vẫn cần quy tắc tương thích.

Ví dụ một DTO có thể lưu:

~~~json
{
  "schemaVersion": 1,
  "cartId": "cart-123",
  "shippingCode": "EXPRESS"
}
~~~

Phiên bản mới có thể bổ sung field:

~~~json
{
  "schemaVersion": 2,
  "cartId": "cart-123",
  "shipping": {
    "method": "EXPRESS"
  }
}
~~~

Nếu phiên bản mới chỉ biết schemaVersion 2, nó có thể không đọc hoặc không hiểu đúng dữ liệu version 1. Một chiến lược tốt là có lớp chuyển đổi rõ ràng:

~~~java
CheckoutDraftV2 upgrade(CheckoutDraftV1 oldValue) {
    return new CheckoutDraftV2(
        oldValue.cartId(),
        ShippingMethod.fromLegacyCode(oldValue.shippingCode())
    );
}
~~~

Đoạn code minh họa cho thấy việc chuyển đổi được thực hiện rõ ràng và có thể kiểm thử. Cần xác định hành vi với mã cũ không nhận diện được: từ chối bản nháp, đặt trạng thái cần người dùng xác nhận hoặc yêu cầu khởi tạo lại.

Khi dùng Jackson:

- Quyết định rõ cách xử lý field không biết và field bị thiếu.
- Đặt giá trị mặc định có chủ đích cho field mới.
- Kiểm soát enum và tên property.
- Tránh bật polymorphic default typing rộng cho dữ liệu không tin cậy.
- Nếu cần metadata kiểu, dùng allowlist type an toàn và kiểm thử với dữ liệu cũ.
- Gắn schema version cho DTO có vòng đời dài.
- Không coi việc bỏ qua unknown property là đủ để bảo đảm tương thích nghiệp vụ.

Một JSON deserialize thành công vẫn có thể mang giá trị sai nghĩa. Ví dụ field cũ shippingCode bị bỏ qua mà không chuyển đổi, object mới vẫn tạo được nhưng mất lựa chọn vận chuyển. Kiểm thử phải xác nhận cả giá trị và ý nghĩa sau chuyển đổi.

## 6. Thiết kế thuộc tính session ổn định qua nhiều phiên bản

Có thể giảm rủi ro bằng cách định nghĩa các DTO session nhỏ, ít thay đổi và tách khỏi entity nghiệp vụ.

Ví dụ:

~~~java
public record ActiveCartReference(
        String cartId,
        int schemaVersion
) implements Serializable {
}
~~~

Nếu dùng Java record hoặc kiểu dữ liệu mới, cần xác nhận serializer và phiên bản Java/framework hỗ trợ. Với Java serialization, record cũng cần được kiểm thử thực tế; đừng giả định mọi thay đổi record đều tương thích.

Một số hướng thiết kế:

- Lưu ID tham chiếu thay vì toàn bộ object nghiệp vụ.
- Dùng String hoặc kiểu vô hướng có định dạng ổn định khi phù hợp.
- Dùng mã trạng thái ổn định thay vì ordinal của enum.
- Không lưu object từ thư viện nếu không kiểm soát vòng đời và phiên bản.
- Đặt namespace cho tên thuộc tính như app.checkoutDraft.
- Nếu cần migration, có thể version hóa tên thuộc tính hoặc payload.
- Giữ logic chuyển đổi ở một lớp mapper riêng và kiểm thử bằng fixture cũ.

Không sử dụng enum ordinal làm dữ liệu bền vững. Nếu thứ tự enum thay đổi, cùng một số nguyên có thể mang ý nghĩa khác. Lưu tên hoặc mã ổn định, đồng thời có quy tắc ánh xạ giá trị cũ.

## 7. Kiểm thử bằng fixture do phiên bản cũ tạo ra

Một trong những cách đáng tin cậy nhất là giữ fixture session được tạo bởi đúng artifact cũ. Fixture phải phản ánh dữ liệu thực tế của serializer và dependency ở phiên bản đó.

Có hai cách phổ biến:

### Cách A: Chạy hai phiên bản ứng dụng tuần tự

1. Khởi chạy phiên bản cũ với Redis/JDBC test store riêng.
2. Tạo session qua luồng đăng nhập hoặc API test.
3. Lưu các thuộc tính đại diện cho dữ liệu production, nhưng dùng dữ liệu giả.
4. Ghi lại session ID và giữ nguyên dữ liệu trong store.
5. Dừng phiên bản cũ.
6. Khởi chạy phiên bản mới với cùng repository, namespace/schema và serializer tương thích.
7. Gửi request với cookie/session ID cũ hoặc gọi repository findById.
8. Xác nhận session và các thuộc tính quan trọng đọc được đúng.

Cách này kiểm tra cả quá trình ghi ở phiên bản cũ và đọc ở phiên bản mới, bao gồm framework, serializer và repository.

### Cách B: Lưu fixture serialized

Phiên bản cũ có thể tạo fixture byte hoặc JSON đại diện cho thuộc tính session. Fixture được lưu trong test resources kèm thông tin nguồn:

~~~text
src/test/resources/session-fixtures/
  release-1.8/
    checkout-draft.bin
    fixture-metadata.json
~~~

Metadata fixture nên ghi:

- Phiên bản ứng dụng tạo fixture.
- Phiên bản Java.
- Phiên bản Spring Session và Spring Security.
- Serializer và cấu hình liên quan.
- Tên class/thuộc tính được lưu.
- Mục đích test và schema version.
- Dữ liệu đã được làm giả hoặc loại bỏ thông tin cá nhân.

Không lấy trực tiếp cookie/session ID hoặc dữ liệu người dùng thật từ production để đưa vào repository. Fixture nên dùng ID giả và dữ liệu tổng hợp, không chứa token, mật khẩu, thông tin cá nhân hoặc SecurityContext thật.

Fixture serialized phải được tạo bởi artifact cũ thực sự. Nếu dùng class mới để tạo object rồi serialize, test chỉ chứng minh phiên bản mới đọc dữ liệu của chính nó, không chứng minh khả năng tương thích ngược.

## 8. Kiểm thử repository với session cũ

Với Spring Session Redis, có thể kiểm thử repository bằng cách dùng cùng Redis test instance và cùng namespace. Với JDBC, cần dùng schema và bảng session tương ứng của ứng dụng.

Một test khái niệm:

~~~java
@Test
void readsSessionWrittenByPreviousRelease() {
    String sessionId = legacyFixtureLoader.loadIntoTestRepository();

    Session session = repository.findById(sessionId);

    assertThat(session).isNotNull();
    assertThat(session.getAttribute("app.activeCartId"))
            .isEqualTo("cart-123");
}
~~~

Đây là ví dụ khái niệm; cách nạp fixture phụ thuộc serializer và repository. Với Redis, fixture có thể được nạp bởi phiên bản cũ hoặc bằng một test utility sử dụng chính serializer cũ. Với JDBC, fixture phải tương thích với schema và cách serialize thuộc tính của phiên bản cũ.

Đừng chỉ kiểm tra session khác null. Hãy xác nhận:

- Thuộc tính bảo mật cần thiết đọc được và có kiểu đúng.
- Principal vẫn có tên và authority mong đợi.
- Các ID tham chiếu vẫn hợp lệ theo dữ liệu nghiệp vụ test.
- Giá trị enum/mã trạng thái được chuyển đổi đúng.
- Field mới có default đúng.
- Field đã bỏ không làm hỏng logic.
- TTL và lastAccessedTime vẫn có ý nghĩa.
- Session có thể được cập nhật và lưu lại bởi phiên bản mới.

Nếu phiên bản mới đọc session thành công nhưng lần lưu tiếp theo làm hỏng dữ liệu đối với node cũ, rolling deployment vẫn chưa an toàn. Cần kiểm tra cả chiều ghi và đọc trong giai đoạn hai phiên bản cùng chạy.

## 9. Kiểm thử Spring Security và principal cũ

Session đăng nhập thường chứa SecurityContext. Nội dung có thể bao gồm Authentication, principal, authorities và chi tiết xác thực. Các class này có thể thay đổi khi nâng cấp Spring Security hoặc class principal của ứng dụng.

Một bộ kiểm thử cần xác nhận:

1. Phiên bản cũ tạo session sau khi đăng nhập.
2. Session chứa SecurityContext đúng như cấu hình hiện hành.
3. Phiên bản mới đọc session và xác định đúng principal.
4. Authorities vẫn được diễn giải đúng.
5. Request được bảo vệ vẫn yêu cầu xác thực như mong đợi.
6. Logout và invalidation hoạt động với session cũ.
7. Nếu principal class đã thay đổi, migration hoặc yêu cầu đăng nhập lại được thực hiện có chủ đích.

Không chỉ kiểm tra rằng SecurityContext deserialize được. Hãy xác minh quyền thực tế sau khi đọc. Một Authentication có thể deserialize thành công nhưng authority bị thiếu hoặc sai, gây ra lỗi cấp quyền nghiêm trọng.

Nếu principal là class tùy chỉnh, hãy giữ cấu trúc serialization ổn định hoặc chuyển sang một DTO principal nhỏ với định danh ổn định. Không lưu toàn bộ entity người dùng vào principal nếu không cần thiết.

## 10. Rolling deployment: kiểm tra cả hai chiều đọc và ghi

Trong rolling deployment, node cũ và node mới có thể cùng nhận request trong một khoảng thời gian. Vì vậy, kiểm thử chỉ có phiên bản mới đọc dữ liệu cũ là chưa đủ.

Cần xem xét ma trận:

| Writer | Reader | Mục tiêu |
|---|---|---|
| Phiên bản cũ | Phiên bản mới | Bắt buộc nếu session cũ còn tồn tại sau deploy |
| Phiên bản mới | Phiên bản mới | Bắt buộc cho hoạt động bình thường |
| Phiên bản mới | Phiên bản cũ | Cần nếu node cũ còn phục vụ trong rolling window |
| Phiên bản cũ | Phiên bản cũ | Bảo đảm rollback vẫn hoạt động trong giai đoạn cho phép |

Một quy trình expand-contract thường an toàn hơn:

**Giai đoạn 1 — Expand reader:** phát hành phiên bản có thể đọc cả định dạng cũ và mới, nhưng vẫn ghi định dạng cũ tương thích với các node còn lại.

**Giai đoạn 2 — Drain old nodes:** chờ node cũ rời khỏi load balancer và không còn request nào có thể ghi session theo định dạng cũ.

**Giai đoạn 3 — Switch writer:** bật ghi định dạng mới sau khi mọi node đang hoạt động đều đọc được định dạng mới.

**Giai đoạn 4 — Contract:** sau khi session cũ hết TTL hoặc đã được chuyển đổi, loại bỏ code đọc định dạng cũ trong một lần phát hành sau.

Không nên phát hành phiên bản ghi định dạng mới ngay khi node cũ vẫn còn hoạt động nếu node cũ không thể đọc dữ liệu mới. Một request có thể ghi session ở node mới rồi request kế tiếp được định tuyến tới node cũ và gây lỗi.

### Rollback cũng cần được tính đến

Nếu phiên bản mới đã ghi dữ liệu session theo format mới, rollback về phiên bản cũ có thể làm session không đọc được. Trước khi phát hành, quyết định:

- Rollback có cần giữ session hiện tại không?
- Phiên bản cũ có đọc được dữ liệu mà phiên bản mới ghi không?
- Có thể tạm thời giữ writer ở format cũ không?
- Nếu không thể tương thích, có chấp nhận yêu cầu người dùng đăng nhập lại sau rollback không?

Rollback ứng dụng không tự rollback dữ liệu session đã ghi vào Redis/JDBC.

## 11. Thay đổi serializer và namespace

Đổi serializer là thay đổi định dạng lưu trữ. Ví dụ, phiên bản cũ dùng Java serialization, phiên bản mới chuyển sang JSON. Nếu dữ liệu cũ vẫn còn, serializer mới có thể không đọc được byte cũ.

Có ba chiến lược thường gặp:

| Chiến lược | Mô tả | Khi phù hợp |
|---|---|---|
| Giữ serializer cũ | Không đổi định dạng session | Khi cần giữ session qua nâng cấp và không cần chuyển format |
| Đọc hai định dạng, chỉ ghi định dạng mới sau khi rollout | Serializer chuyển tiếp nhận dữ liệu cũ và mới | Khi có kế hoạch migration rõ và kiểm soát được hai định dạng |
| Dùng namespace mới | Tách keyspace và yêu cầu session mới | Khi chấp nhận thu hồi session cũ hoặc không thể tương thích |

Nếu đổi namespace, repository mới sẽ không tìm session trong keyspace cũ. Đây có thể là cách cắt phiên có chủ đích, nhưng thường khiến người dùng phải đăng nhập lại. Namespace mới không tự chuyển đổi dữ liệu cũ.

Nếu dùng serializer chuyển tiếp, cần kiểm tra format marker hoặc schema version để chọn decoder. Không thử deserialize tuần tự mọi serializer một cách tùy tiện; cách đó có thể che giấu lỗi dữ liệu, tạo hành vi không xác định và mở rộng bề mặt tấn công.

## 12. Khi session cũ không thể đọc được

Không nên biến mọi lỗi deserialize thành session anonymous một cách âm thầm. Cần phân biệt:

- Session không tồn tại hoặc đã hết hạn: repository không tìm thấy session hợp lệ.
- Session tồn tại nhưng một thuộc tính không đọc được: lỗi dữ liệu/serializer.
- Repository không kết nối được: lỗi hạ tầng.
- Session đọc được nhưng dữ liệu nghiệp vụ tham chiếu đã mất: lỗi trạng thái nghiệp vụ hoặc tham chiếu cũ.

Chính sách xử lý phụ thuộc loại thuộc tính:

| Thuộc tính lỗi | Hành động có thể chọn |
|---|---|
| Locale hoặc tùy chọn giao diện | Bỏ thuộc tính và dùng mặc định |
| Danh sách gần đây | Khởi tạo lại nếu dữ liệu không quan trọng |
| Giỏ hàng tham chiếu bằng ID | Tải lại từ nguồn nghiệp vụ hoặc yêu cầu người dùng chọn lại |
| Checkout draft | Chuyển đổi có kiểm soát hoặc yêu cầu bắt đầu lại |
| SecurityContext/Authentication | Không cấp quyền; yêu cầu xác thực lại theo chính sách |
| Token hoặc dữ liệu xác thực | Thu hồi/đăng nhập lại theo cơ chế bảo mật; không tự khôi phục từ dữ liệu lỗi |

Nếu deserialize toàn bộ session thất bại trong repository, ứng dụng có thể không truy cập được từng thuộc tính riêng lẻ. Không bắt exception chung trong filter rồi tiếp tục request như anonymous nếu điều đó che giấu lỗi Redis/JDBC hoặc làm sai luồng bảo mật. Hãy để lỗi được ghi nhận rõ, trả phản hồi phù hợp và có quy trình thu hồi session bị hỏng.

Nếu quyết định xóa session lỗi, cần xác định chính xác session ID và bảo đảm chỉ xóa session đó qua API repository sau khi phân biệt với lỗi hạ tầng tạm thời. Không dùng thao tác xóa wildcard key để xử lý hàng loạt lỗi deserialize.

## 13. Bộ kiểm thử tương thích nên có những trường hợp nào?

Một ma trận kiểm thử trước release có thể gồm:

| Ca kiểm thử | Dữ liệu đầu vào | Điều cần xác nhận |
|---|---|---|
| Session cũ tối thiểu | Chỉ có metadata và một thuộc tính đơn giản | Repository mới tìm và đọc được |
| Session cũ đầy đủ | Có các thuộc tính thường dùng trong production | Tất cả thuộc tính quan trọng deserialize đúng |
| SecurityContext cũ | Authentication/principal từ phiên bản trước | Principal và authority được khôi phục đúng |
| Field mới được thêm | Payload cũ không có field mới | Default mới hợp lệ |
| Field bị xóa | Payload cũ có field không còn dùng | Không gây lỗi hoặc sai nghiệp vụ |
| Enum thay đổi | Payload chứa mã enum cũ | Mapping giá trị cũ rõ ràng |
| Class đổi package | Payload tham chiếu tên class cũ | Migration hoặc fallback có chủ đích |
| Serializer thay đổi | Byte/JSON theo format cũ | Reader chuyển tiếp xử lý đúng hoặc từ chối có kiểm soát |
| Session hết hạn | Dữ liệu cũ đã quá TTL | Không khôi phục session đã hết hạn |
| Session bị logout | ID cũ đã bị xóa | Request không còn được xác thực |
| Rolling deployment | Node cũ và mới cùng đọc/ghi | Không có node nào ghi format mà node khác không đọc được |
| Rollback | Phiên bản cũ đọc dữ liệu đã ghi sau nâng cấp | Rollback có thể tiếp tục hoặc buộc đăng nhập lại theo kế hoạch |

Ngoài kiểm thử dữ liệu, cần kiểm thử qua HTTP filter chain. Một test chỉ gọi ObjectMapper hoặc ObjectInputStream không chứng minh Spring Session repository và Spring Security có thể đọc session thực tế.

## 14. Ví dụ kiểm thử hai phiên bản bằng Redis test store

Một quy trình integration test có thể được tổ chức như sau:

~~~text
1. Start Redis test container với namespace riêng.
2. Chạy helper hoặc artifact của release cũ.
3. Đăng nhập bằng test principal và tạo session.
4. Lưu session ID cùng fixture metadata.
5. Dừng helper cũ, giữ Redis không bị xóa.
6. Khởi động ứng dụng phiên bản mới với cùng Redis/namespace.
7. Gửi request với cookie session cũ.
8. Xác nhận principal, authority và thuộc tính ứng dụng.
9. Cập nhật một thuộc tính bằng phiên bản mới.
10. Nếu còn hỗ trợ rollback, chạy reader cũ và xác nhận format vẫn đọc được.
11. Xóa test store sau khi hoàn tất.
~~~

Mẫu kiểm thử HTTP:

~~~java
mockMvc.perform(get("/account")
        .cookie(new Cookie("SESSION", legacySessionId)))
    .andExpect(status().isOk())
    .andExpect(authenticated().withUsername("test-user"));
~~~

Ví dụ này chỉ minh họa cách gửi cookie cũ qua filter chain. Test cần ứng dụng đã cấu hình Spring Session, repository thật trong test và endpoint bảo vệ phù hợp. Nếu dùng MockHttpSession trực tiếp, test có thể bỏ qua quá trình deserialize từ Redis/JDBC và không chứng minh tương thích dữ liệu cũ.

Với JDBC, quy trình tương tự nhưng phải giữ schema session và dữ liệu thuộc tính do phiên bản cũ tạo. Nếu schema thay đổi, cần kiểm thử migration schema riêng với migration dữ liệu thuộc tính.

## 15. Tự động hóa kiểm tra trước khi phát hành

Nên lưu fixture cho các release quan trọng và chạy chúng như một phần của pipeline kiểm thử nâng cấp:

- Mỗi release có thể tạo fixture session đại diện.
- Pipeline của release mới chạy test đọc tất cả fixture còn nằm trong khoảng hỗ trợ.
- Kiểm thử cả serializer và HTTP authentication flow.
- Kiểm tra log không chứa session ID hoặc thông tin xác thực.
- Đặt ngưỡng lỗi: fixture quan trọng không đọc được thì chặn phát hành hoặc yêu cầu quyết định thu hồi session.
- Ghi lại phiên bản fixture và serializer để biết dữ liệu nào đang được kiểm tra.
- Loại bỏ fixture cũ khi thời hạn session tối đa đã qua và chính sách hỗ trợ không còn yêu cầu đọc chúng.

Không cần giữ fixture của mọi commit. Hãy chọn các mốc release có thay đổi serializer, class principal, Spring Security, Java hoặc cấu trúc thuộc tính session. Fixture càng đại diện cho dữ liệu thực tế thì test càng có giá trị.

## 16. Checklist nâng cấp an toàn

Trước khi triển khai phiên bản mới, xác nhận:

- Đã liệt kê các thuộc tính session có thể còn tồn tại từ release trước.
- Đã biết serializer và dependency thực tế của phiên bản cũ.
- Đã có fixture được tạo bởi artifact cũ, không phải chỉ tạo bằng class mới.
- Đã kiểm tra Java serialization UID, class name, field type và enum.
- Đã kiểm tra JSON schema, type metadata và giá trị mặc định.
- Đã kiểm thử SecurityContext, principal và authorities cũ.
- Đã thử đọc session cũ qua repository và HTTP filter chain.
- Đã kiểm thử ghi mới rồi đọc lại, và đọc chéo giữa node cũ/mới khi rolling deployment.
- Đã xác định rollback có đọc được dữ liệu session mới hay cần buộc đăng nhập lại.
- Đã có chính sách cho session lỗi: khôi phục, bỏ thuộc tính không quan trọng, yêu cầu xác thực lại hoặc thu hồi.
- Đã có metric/log để phân biệt missing session, deserialize failure và repository outage.
- Không dùng dữ liệu người dùng thật làm fixture hoặc ghi session ID vào log.

Một session cũ đọc được chỉ khi repository, serializer, class thuộc tính và framework cùng hiểu định dạng đã lưu. Hãy kiểm thử bằng dữ liệu do phiên bản cũ thực sự tạo ra, xác nhận cả nội dung nghiệp vụ lẫn quyền xác thực, rồi thử tình huống hai phiên bản cùng chạy và rollback. Nếu không thể duy trì tương thích, hãy chọn thời điểm thu hồi session và yêu cầu đăng nhập lại một cách có chủ đích thay vì để lỗi deserialize xuất hiện ngẫu nhiên trong production.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/)
- [Jackson Databind — Deserialization Features](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)

