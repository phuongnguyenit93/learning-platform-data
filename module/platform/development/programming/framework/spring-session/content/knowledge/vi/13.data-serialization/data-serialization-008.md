# Thay đổi cấu trúc đối tượng giữa các phiên bản ứng dụng

Spring Session lưu các thuộc tính HttpSession trong một repository như Redis hoặc JDBC để request tiếp theo, thậm chí một instance khác, có thể khôi phục cùng dữ liệu. Dữ liệu đó thường tồn tại lâu hơn một lần chạy ứng dụng. Vì vậy, khi triển khai phiên bản mới, cấu trúc lớp Java hoặc schema dữ liệu có thể đã thay đổi trong khi kho phiên vẫn còn các đối tượng được ghi bởi phiên bản cũ.

Đây là vấn đề tương thích tuần tự hóa. Một phiên bản ứng dụng mới phải đọc được dữ liệu phiên cũ trong thời gian chuyển đổi, hoặc phải có kế hoạch chuyển đổi/loại bỏ phiên cũ có kiểm soát. Nếu không, request có thể thất bại khi deserialize thuộc tính, mất một phần trạng thái hoặc buộc người dùng đăng nhập lại ngoài dự kiến.

Bài học tập trung vào cách thay đổi cấu trúc đối tượng được lưu trong Spring Session khi nâng cấp ứng dụng, đặc biệt trong môi trường nhiều instance và triển khai rolling hoặc blue-green. Nguyên tắc cốt lõi là coi dữ liệu phiên như một hợp đồng dữ liệu tồn tại qua nhiều phiên bản phần mềm.

## 1. Vì sao thay đổi lớp có thể làm hỏng phiên cũ?

Một session có thể chứa các đối tượng Java do ứng dụng định nghĩa, ví dụ Cart, UserPreferences hoặc trạng thái quy trình thanh toán. Khi request kết thúc, Spring Session ghi các thuộc tính đó qua serializer của repository. Request sau đọc lại dữ liệu và khôi phục đối tượng.

Giả sử phiên bản 1 lưu:

~~~java
public class UserPreferences implements Serializable {
    private String theme;
    private String language;
}
~~~

Ở phiên bản 2, nhóm phát triển đổi tên lớp, đổi kiểu field hoặc thay cấu trúc lồng nhau:

~~~java
public class UserPreferences implements Serializable {
    private Theme theme;
    private Locale language;
    private boolean compactLayout;
}
~~~

Các byte đã lưu từ phiên bản 1 không tự biến thành cấu trúc mới. Kết quả phụ thuộc serializer và mức độ tương thích giữa hai schema. Với Java native serialization, một thay đổi không tương thích có thể gây InvalidClassException hoặc lỗi khôi phục trường. Với JSON, dữ liệu có thể đọc được nhưng field cũ, field thiếu hoặc type metadata có thể khiến quá trình mapping thất bại hoặc tạo giá trị mặc định ngoài ý muốn.

Một số nguyên nhân thường gặp:

- Đổi tên class hoặc package được ghi trong metadata kiểu.
- Thay đổi serialVersionUID hoặc để Java tự tính UID rồi vô tình làm UID thay đổi.
- Đổi kiểu field, ví dụ String thành một enum hoặc object phức tạp.
- Đổi tên field khiến serializer không còn ánh xạ được dữ liệu cũ.
- Xóa field mà logic nghiệp vụ mới vẫn giả định dữ liệu luôn có giá trị.
- Thay đổi cấu trúc collection hoặc kiểu phần tử bên trong.
- Đổi serializer, ObjectMapper hoặc chính sách polymorphic type giữa hai phiên bản.
- Thay đổi classpath khiến class cũ không còn tồn tại khi deserialize.

Không phải mọi thay đổi đều gây lỗi. Thêm một field có thể tương thích với một số serializer nếu field mới có thể nhận giá trị mặc định. Nhưng tương thích kỹ thuật không đồng nghĩa tương thích nghiệp vụ: giá trị mặc định null, false hoặc 0 có thể làm sai quy trình nếu code mới giả định field đã được thiết lập.

## 2. Vị trí của serializer trong Spring Session

Spring Session quản lý vòng đời phiên và ủy quyền việc lưu/đọc dữ liệu cho repository. Serializer là thành phần chuyển đổi thuộc tính phiên giữa object trong JVM và dạng dữ liệu lưu trữ.

Luồng khái quát:

    Controller / Spring Security
              |
              | setAttribute(...)
              v
          HttpSession
              |
              v
      SessionRepositoryFilter
              |
              v
       SessionRepository
              |
              | serialize thuộc tính
              v
          Redis / JDBC
              |
              | deserialize khi đọc
              v
       Object trong JVM

Các lớp repository và serializer cụ thể phụ thuộc module, phiên bản và cấu hình:

| Thành phần | Điều cần xác định |
|---|---|
| Spring Session Redis | Serializer dùng cho dữ liệu phiên và từng session attribute |
| Spring Session JDBC | Cách attribute được chuyển thành dữ liệu lưu trong cột tương ứng |
| Serializer tùy chỉnh | Format, type metadata, quy tắc tương thích và cách xử lý dữ liệu cũ |
| Ứng dụng | Các class thực tế được đặt trong HttpSession và vòng đời của chúng |

Không nên giả định Redis và JDBC có cùng serializer hoặc cùng format lưu trữ. Cũng không nên dựa vào tên key, cột hoặc byte format nội bộ như một hợp đồng ổn định giữa mọi phiên bản. Trước khi nâng cấp, hãy xác định repository và serializer thực tế đang chạy bằng cấu hình ứng dụng và tài liệu đúng phiên bản.

## 3. Tương thích của Java native serialization

Java serialization có thể được dùng để ghi object Serializable thành byte stream. Khi khôi phục, JVM kiểm tra thông tin lớp, bao gồm tên lớp và serialVersionUID.

Ví dụ khai báo UID tường minh:

~~~java
public class CartSnapshot implements Serializable {

    private static final long serialVersionUID = 1L;

    private List<String> productCodes;
    private String currency;
}
~~~

Nếu không khai báo serialVersionUID, Java có thể tính một giá trị dựa trên cấu trúc lớp. Khi thay đổi class, UID được tính có thể thay đổi và dữ liệu cũ có thể không deserialize được. Khai báo UID tường minh giúp kiểm soát định danh phiên bản serialization.

Tuy nhiên, giữ nguyên serialVersionUID không tự làm mọi thay đổi tương thích. JVM vẫn cần xử lý được sự khác biệt về field và kiểu dữ liệu. Một số thay đổi có thể được hỗ trợ theo quy tắc Java serialization, nhưng đổi kiểu field, đổi class hoặc thay đổi cấu trúc object graph có thể gây lỗi hoặc làm mất dữ liệu.

Một số nguyên tắc khi dùng Java serialization:

- Khai báo serialVersionUID rõ ràng cho lớp được lưu trong session.
- Không tùy tiện đổi kiểu hoặc đổi tên class/package nếu dữ liệu cũ còn tồn tại.
- Khi thêm field, xác định giá trị mặc định và cách chuyển đổi dữ liệu cũ.
- Khi xóa field, xác nhận code mới không còn phụ thuộc vào field đó.
- Với thay đổi phức tạp, dùng readObject/readResolve hoặc lớp chuyển đổi có kiểm thử; không dùng chúng để che giấu một schema không rõ ràng.
- Giữ class cũ trong classpath trong giai đoạn cần đọc dữ liệu cũ nếu chiến lược migration yêu cầu.

serialVersionUID là một phần của hợp đồng serialization, không phải số phiên bản ứng dụng. Không tăng UID theo thói quen sau mọi lần sửa code nếu vẫn muốn đọc dữ liệu cũ; ngược lại, cũng không giữ UID cũ một cách máy móc khi cấu trúc đã thay đổi không tương thích.

## 4. Tương thích khi dùng JSON hoặc serializer dựa trên schema

JSON thường dễ kiểm tra và hỗ trợ nhiều loại client/service hơn byte stream Java, nhưng vẫn cần chính sách schema. Một JSON cũ có thể chứa:

~~~json
{
  "theme": "dark",
  "language": "vi"
}
~~~

Phiên bản mới có thể mong đợi:

~~~json
{
  "theme": {
    "mode": "DARK",
    "contrast": "NORMAL"
  },
  "localeTag": "vi-VN",
  "compactLayout": false
}
~~~

Đây là thay đổi schema lớn: theme đổi từ chuỗi thành object, language đổi tên và compactLayout được thêm. Serializer JSON không thể tự suy luận đầy đủ ý nghĩa mới chỉ từ dữ liệu cũ. Cần một bước chuyển đổi rõ ràng.

Với JSON, nên ưu tiên DTO ổn định, field có ý nghĩa rõ ràng và schema version tường minh. Có thể xử lý field mới bị thiếu bằng default hợp lý, nhưng phải phân biệt dữ liệu cũ thiếu field với dữ liệu người dùng cố ý chọn giá trị rỗng.

Nếu dùng Jackson hoặc serializer có type metadata:

- Giữ tên type/schema ổn định nếu dữ liệu tồn tại lâu.
- Không để tên package Java trở thành hợp đồng lưu trữ không kiểm soát.
- Cấu hình xử lý field không biết và field thiếu theo chủ đích.
- Không bật polymorphic default typing rộng rãi cho dữ liệu không tin cậy.
- Kiểm thử dữ liệu JSON cũ bằng đúng ObjectMapper và module đang triển khai.
- Cân nhắc serializer theo DTO thay vì serialize trực tiếp entity hoặc object framework.

JSON dễ đọc hơn không có nghĩa tự động an toàn hơn. Type metadata có thể tạo rủi ro nếu dữ liệu không đáng tin cậy và deserializer cho phép khởi tạo type tùy ý. Session store cần được bảo vệ quyền truy cập và đường truyền; không xem dữ liệu Redis/JDBC là nguồn luôn đáng tin chỉ vì nó nằm phía server.

## 5. Đưa schema version vào dữ liệu session

Khi cấu trúc thuộc tính thay đổi qua nhiều lần triển khai, có thể thêm một trường version vào DTO hoặc envelope lưu trong session.

Ví dụ:

~~~java
public class CartState implements Serializable {

    private static final long serialVersionUID = 1L;

    private int schemaVersion;
    private List<CartLineState> lines;
    private String currency;
}
~~~

Khi đọc dữ liệu, ứng dụng kiểm tra schemaVersion rồi chuyển đổi sang cấu trúc hiện tại. Ví dụ một quy trình chuyển đổi:

~~~java
CartState migrate(CartState state) {
    if (state.getSchemaVersion() == 1) {
        state.setCurrency("VND");
        state.setSchemaVersion(2);
    }

    if (state.getSchemaVersion() == 2) {
        // Áp dụng các thay đổi từ schema 2 lên schema 3.
        state.setSchemaVersion(3);
    }

    return state;
}
~~~

Đoạn mã minh họa luồng nâng cấp từng bước. Trong ứng dụng thực tế, nên dùng DTO version riêng cho từng schema cũ và hàm chuyển đổi có kiểu rõ ràng thay vì sửa trực tiếp object cũ nếu cấu trúc đã thay đổi mạnh.

Một thiết kế khác là envelope:

~~~json
{
  "schemaVersion": 3,
  "payload": {
    "currency": "VND",
    "lines": []
  }
}
~~~

Envelope cho phép xác định format trước khi chuyển payload. Nếu có nhiều kiểu dữ liệu session, có thể dùng version riêng theo loại thuộc tính thay vì một version chung cho toàn bộ session.

Không lưu version ở một nơi mà serializer không thể đọc trước khi deserialize class cũ. Với Java native serialization, nếu class không còn tương thích thì lỗi có thể xảy ra trước khi code migration nhận được object. Trong trường hợp đó, cần giữ class tương thích, dùng serializer trung gian có thể đọc dữ liệu cũ hoặc chủ động loại bỏ phiên cũ.

## 6. Chiến lược expand-contract cho rolling deployment

Trong triển khai nhiều instance, phiên bản cũ và mới có thể cùng nhận request trong một khoảng thời gian. Đây là lúc tương thích đọc/ghi quan trọng nhất.

Giả sử V1 lưu schema 1 và V2 lưu schema 2. Nếu V2 ghi schema 2 trong khi instance V1 vẫn có thể đọc cùng session, V1 có thể thất bại khi deserialize hoặc bỏ qua dữ liệu mới. Do đó, không nên để phiên bản mới ghi format mà phiên bản cũ không đọc được trước khi các instance cũ đã được loại khỏi luồng request.

Chiến lược expand-contract gồm các pha:

1. **Expand reader:** triển khai phiên bản trung gian có thể đọc schema cũ và schema mới, nhưng vẫn ghi schema cũ hoặc format tương thích với cả hai phiên bản.
2. **Hoàn tất rollout reader:** bảo đảm tất cả instance đang hoạt động đều hiểu format mới.
3. **Switch writer:** bật ghi schema mới sau khi không còn instance cũ chỉ đọc được schema cũ.
4. **Migrate data:** chuyển dữ liệu session còn sống theo kiểu lazy khi đọc hoặc qua job có kiểm soát nếu repository hỗ trợ.
5. **Contract:** sau khi dữ liệu cũ đã hết hạn hoặc được chuyển đổi, bỏ code đọc schema cũ và loại bỏ lớp/field cũ.

Bảng minh họa:

| Giai đoạn | Instance đang chạy | Đọc được | Ghi ra |
|---|---|---|---|
| Trước rollout | V1 | Schema 1 | Schema 1 |
| Expand | V1 + V1-compatible reader | Schema 1 | Schema 1 |
| Reader rollout hoàn tất | V2 reader-compatible | Schema 1 và 2 | Tạm thời schema 1 |
| Switch writer | V2 | Schema 1 và 2 | Schema 2 |
| Contract hoàn tất | V2 mới | Schema 2 | Schema 2 |

Tên V1-compatible reader trong bảng là một phiên bản trung gian, không nhất thiết phải là một release riêng. Điều quan trọng là trong mọi thời điểm có thể có nhiều instance cùng đọc một phiên, mọi writer phải tạo dữ liệu mà tất cả reader đang hoạt động có thể xử lý.

Nếu không thể tạo phiên bản đọc tương thích, hãy cân nhắc một cửa sổ bảo trì, đổi namespace session store và yêu cầu người dùng xác thực lại. Đây là lựa chọn có tác động người dùng nhưng đôi khi an toàn hơn việc để request ngẫu nhiên thất bại trong rollout.

## 7. Lazy migration khi đọc session

Một cách phổ biến để chuyển đổi session là lazy migration. Khi request đọc phiên cũ, ứng dụng nhận diện schema version, chuyển đổi sang cấu trúc hiện tại rồi lưu lại.

Luồng:

    Request tải session
            |
            v
      Đọc schemaVersion
            |
       +----+----+
       |         |
     Mới nhất    Cũ
       |         |
       v         v
    Sử dụng    Chuyển đổi
       |         |
       |         v
       |      Cập nhật DTO
       |         |
       +----+----+
            |
            v
       Lưu session
            |
            v
       Xử lý request

Lazy migration phù hợp khi số session còn sống lớn nhưng chỉ một phần được sử dụng. Phiên không được truy cập sẽ tự hết hạn theo TTL và không cần chuyển đổi. Tuy nhiên, migration phải chạy an toàn khi request đồng thời đọc cùng session.

Một service có thể đóng gói việc đọc và chuyển đổi:

~~~java
public CurrentCartState loadCurrentCart(HttpSession session) {
    Object stored = session.getAttribute("cartState");

    CurrentCartState current = cartStateMapper.toCurrent(stored);

    session.setAttribute("cartState", current);
    return current;
}
~~~

cartStateMapper chịu trách nhiệm nhận diện kiểu/schema cũ và chuyển sang DTO hiện tại. Việc set lại thuộc tính giúp đánh dấu thay đổi theo chính sách lưu session phù hợp. Đoạn mã là minh họa; mapper cần xử lý rõ các phiên bản được hỗ trợ và từ chối dữ liệu không thể chuyển đổi.

Không nên thực hiện migration trong mọi request nếu session đã ở schema mới. Hãy kiểm tra version, chỉ chuyển đổi khi cần và ghi metric số phiên được migrate để theo dõi tiến độ.

## 8. Migration chủ động và xử lý session không thể đọc

Với một số thay đổi, lazy migration không đủ. Ví dụ, cần chuyển đổi một thuộc tính lớn hoặc loại bỏ dữ liệu cũ có vấn đề. Có thể cần job migration chủ động, nhưng phải hiểu repository và API truy vấn.

Nếu repository hỗ trợ tìm phiên theo ID hoặc principal index, job có thể xử lý theo từng lô. Tránh quét toàn bộ Redis keyspace hoặc sửa trực tiếp cấu trúc nội bộ khi không có hợp đồng API. Job nên:

- Đọc một nhóm session có giới hạn.
- Xác định schema version của từng thuộc tính.
- Chuyển đổi dữ liệu bằng mapper đã kiểm thử.
- Ghi phiên qua SessionRepository.
- Ghi nhận kết quả, lỗi và số lần thử.
- Có thể chạy lại mà không làm hỏng dữ liệu đã chuyển đổi.

Nếu session không deserialize được, không thể luôn dùng code migration thông thường vì object chưa được tạo thành công. Các lựa chọn gồm:

1. Giữ lại class cũ và serializer tương thích đủ lâu để đọc rồi chuyển đổi.
2. Viết công cụ chuyển đổi chuyên biệt đọc format cũ, sau đó ghi format mới qua repository.
3. Đánh dấu hoặc xóa các phiên không thể phục hồi theo chính sách đã thống nhất.
4. Đổi namespace session store và yêu cầu đăng nhập lại nếu dữ liệu cũ không đáng giữ hoặc rủi ro chuyển đổi quá cao.

Không bắt lỗi deserialize rồi âm thầm tạo session mới trong mọi trường hợp. Điều đó có thể che giấu lỗi dữ liệu, làm mất giỏ hàng hoặc khiến trạng thái xác thực biến mất mà không có quan sát. Nếu buộc phải loại bỏ phiên, hãy ghi metric và log có mã tương quan, không ghi session ID thô.

## 9. Chọn DTO ổn định cho session

Không nên lưu toàn bộ object graph của domain hoặc framework vào HttpSession. Entity JPA, Hibernate proxy, service bean, request object, connection, lambda hoặc class nội bộ thường gắn với cấu trúc runtime và thay đổi nhanh.

Nên tạo DTO dành riêng cho session:

~~~java
public class CheckoutSessionState implements Serializable {

    private static final long serialVersionUID = 1L;

    private int schemaVersion = 1;
    private String cartReference;
    private String currentStep;
    private String localeTag;
}
~~~

DTO chỉ chứa dữ liệu nhỏ cần thiết để tiếp tục tương tác. Ví dụ, thay vì lưu cả entity Cart có nhiều quan hệ JPA, có thể lưu cartReference hoặc danh sách mã sản phẩm. Khi request tiếp theo chạy, service tải dữ liệu nghiệp vụ mới nhất từ database.

Lợi ích:

- Ít phụ thuộc vào entity và framework.
- Dễ kiểm soát schema version.
- Giảm kích thước session và chi phí serialization.
- Dễ viết migration giữa các phiên bản.
- Tránh vô tình lưu dữ liệu nhạy cảm hoặc trạng thái không còn hợp lệ.

DTO ổn định không có nghĩa không bao giờ thay đổi. Nó chỉ tạo một hợp đồng nhỏ, có chủ đích, để thay đổi có thể được quản lý bằng version và migration.

## 10. Phối hợp với TTL và vòng đời session

Session thường có thời hạn không hoạt động. TTL giúp các session cũ tự được loại bỏ, nhưng không nên coi TTL là chiến lược migration duy nhất.

Nếu người dùng hoạt động thường xuyên, timeout có thể được gia hạn. Một phiên từ nhiều tháng trước có thể vẫn tồn tại nếu người dùng tiếp tục truy cập. Vì vậy, khi thay schema không tương thích, chờ TTL tự xóa có thể kéo dài hơn dự kiến.

Có thể phối hợp các cách:

- Hỗ trợ đọc schema cũ trong một khoảng thời gian xác định.
- Lazy migration khi session được truy cập.
- Theo dõi số session còn ở schema cũ.
- Đặt thời hạn hỗ trợ phiên bản schema cũ dựa trên chính sách sản phẩm.
- Chủ động invalidate các phiên quá cũ nếu không thể duy trì tương thích.
- Khi đổi serializer hoặc format hoàn toàn, cân nhắc namespace mới và buộc xác thực lại.

TTL của Redis/JDBC là thời hạn của session record, không phải bảo đảm mọi thuộc tính được chuyển đổi hoặc xóa chính xác tại một thời điểm tuyệt đối. Cần theo dõi cả session còn sống lẫn số bản ghi cũ chưa được xử lý.

## 11. Thay đổi serializer và namespace

Đổi serializer là thay đổi hợp đồng lưu trữ. Ví dụ, phiên bản cũ ghi Java serialization trong khi phiên bản mới đọc JSON. Hai định dạng không thể tự hiểu lẫn nhau nếu không có một lớp chuyển đổi.

Trước khi đổi serializer, hãy xác định:

- Dữ liệu session hiện có được serialize bằng serializer nào.
- Serializer mới có thể đọc dữ liệu cũ hay không.
- Type metadata hoặc tên class có được lưu trong payload không.
- Cả phiên bản cũ và mới có cùng đọc/ghi trong giai đoạn rollout không.
- Có thể chuyển đổi dữ liệu qua một định dạng trung gian hay không.
- Thời gian sống tối đa của dữ liệu cũ là bao lâu.

Namespace tách dữ liệu của ứng dụng hoặc thế hệ schema trong Redis. Đổi namespace giúp phiên bản mới không đọc nhầm dữ liệu theo format cũ, nhưng cũng đồng nghĩa không tìm thấy session cũ trong namespace mới. Đây là cách cắt chuyển rõ ràng khi chấp nhận người dùng phải tạo phiên mới hoặc đăng nhập lại.

Không đổi namespace chỉ để né lỗi mà không thông báo tác động. Hãy đánh giá số phiên đang hoạt động, trải nghiệm đăng nhập lại, chính sách bảo mật và kế hoạch rollback. Nếu rollback về phiên bản cũ sau khi phiên bản mới đã ghi format mới, phiên bản cũ có thể không đọc được dữ liệu; rollback cần nằm trong kế hoạch tương thích từ đầu.

## 12. Bảo mật khi deserialize session

Dữ liệu session thường chứa trạng thái xác thực và có thể chứa thông tin cá nhân. Serializer vì thế là ranh giới bảo mật.

Một số nguyên tắc:

- Chỉ ứng dụng và thành phần được phép mới có quyền đọc/ghi kho session.
- Bảo vệ Redis/JDBC bằng xác thực, phân quyền mạng và mã hóa đường truyền phù hợp.
- Tránh deserialize dữ liệu không tin cậy bằng cơ chế cho phép khởi tạo class tùy ý.
- Nếu dùng Java serialization, giới hạn class được phép deserialize bằng cơ chế filter phù hợp với phiên bản JVM và thư viện.
- Nếu dùng JSON polymorphic typing, cấu hình allowlist type thay vì bật default typing rộng.
- Không lưu password, private key, access token dài hạn hoặc bí mật không cần thiết trong session.
- Không ghi payload session hoặc session ID vào log để điều tra lỗi.

Khi thay đổi cấu trúc dữ liệu, đừng nới lỏng deserialization policy chỉ để dữ liệu cũ đọc được. Hãy tạo migration có kiểm soát hoặc loại bỏ phiên cũ theo chính sách.

## 13. Kiểm thử tương thích giữa các phiên bản

Kiểm thử chỉ chạy phiên bản mới với session mới không phát hiện lỗi đọc dữ liệu cũ. Cần có fixture được tạo bởi phiên bản trước.

Một bộ kiểm thử hữu ích:

1. Dùng phiên bản cũ tạo session với các thuộc tính đại diện.
2. Lưu payload hoặc session fixture vào môi trường kiểm thử an toàn.
3. Khởi chạy phiên bản mới với cùng serializer/repository và đọc fixture.
4. Xác nhận các field cũ được ánh xạ đúng và field mới có giá trị mặc định hợp lệ.
5. Chạy migration và lưu lại session theo schema mới.
6. Đọc lại bằng phiên bản mới để xác nhận round-trip.
7. Trong chiến lược rolling, xác nhận phiên bản cũ không nhận dữ liệu mới trước khi bị loại khỏi traffic.
8. Kiểm thử class rename, field rename, đổi type, nested object và enum nếu các thay đổi đó nằm trong kế hoạch.
9. Kiểm thử dữ liệu hỏng hoặc schema version không được hỗ trợ.
10. Kiểm thử session hết hạn, invalidate và logout sau migration.

Có thể lưu fixture JSON hoặc byte stream do bản build cũ tạo ra trong test resources. Không nên tự dựng payload bằng tay nếu format phụ thuộc serializer; fixture thật cho bằng chứng đáng tin cậy hơn.

Ngoài kiểm thử đơn lẻ, nên chạy một bài kiểm thử tích hợp với hai instance hoặc hai phiên bản ứng dụng trong môi trường staging. Tạo session ở instance cũ, đọc ở instance mới, cập nhật ở instance mới rồi thử đọc ở instance cũ trong giai đoạn compatibility. Đây là cách phát hiện sớm lỗi mixed-version mà unit test không thấy.

## 14. Quy trình nâng cấp schema đề xuất

Khi thay đổi một class đang được lưu trong session, hãy thực hiện theo trình tự:

1. **Kiểm kê:** tìm các thuộc tính session có chứa class bị thay đổi và xác định repository/serializer đang dùng.
2. **Đánh giá tương thích:** phân loại thay đổi là tương thích, cần chuyển đổi hay không thể đọc lại.
3. **Thiết kế DTO/schema:** thêm version hoặc tạo DTO ổn định; định nghĩa default và mapper cho dữ liệu cũ.
4. **Kiểm thử fixture:** đọc dữ liệu được ghi từ phiên bản cũ bằng code mới.
5. **Triển khai reader trước:** bảo đảm mọi instance đang chạy có thể đọc các schema cần hỗ trợ.
6. **Chuyển writer:** chỉ bắt đầu ghi schema mới sau khi không còn reader cũ không tương thích.
7. **Migration và quan sát:** chuyển đổi lazy hoặc theo batch; theo dõi số phiên cũ, lỗi deserialize và tỷ lệ migration.
8. **Contract:** ngừng hỗ trợ schema cũ sau khi dữ liệu đã được chuyển đổi hoặc hết hạn theo chính sách.
9. **Chuẩn bị rollback:** bảo đảm phiên bản rollback đọc được dữ liệu đã ghi, hoặc có kế hoạch namespace/cắt phiên rõ ràng.

Đối với thay đổi không tương thích lớn, lựa chọn an toàn có thể là tạo namespace session mới và yêu cầu xác thực lại. Đối với thay đổi nhỏ, DTO có version và lazy migration thường giữ trải nghiệm tốt hơn.

## Kết luận

Thay đổi cấu trúc đối tượng trong session là thay đổi hợp đồng dữ liệu tồn tại qua nhiều phiên bản ứng dụng. Kết quả phụ thuộc serializer, class metadata, schema và thời gian sống của phiên. Hãy xác định serializer thực tế, dùng DTO nhỏ và ổn định, quản lý schema version, viết migration có thể chạy lặp lại và áp dụng expand-contract khi rolling deployment. Kiểm thử bằng dữ liệu thật do phiên bản cũ tạo ra, theo dõi session chưa migrate và chỉ loại bỏ khả năng đọc schema cũ khi chắc chắn không còn instance hoặc dữ liệu cần nó.
