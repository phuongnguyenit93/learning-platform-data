# serialVersionUID và tương thích của dữ liệu Java đã được lưu

Spring Session lưu các thuộc tính phiên trong repository như Redis hoặc JDBC. Nếu ứng dụng dùng Java native serialization để chuyển đối tượng thành byte và lưu vào kho, dữ liệu đó có thể được đọc lại bởi một instance khác hoặc bởi phiên bản ứng dụng mới hơn. Khi lớp Java thay đổi giữa các lần triển khai, dữ liệu đã lưu có thể không còn tương thích.

serialVersionUID là mã phiên bản được Java Serialization dùng để kiểm tra tính tương thích của lớp Serializable khi ghi và đọc object stream. Khai báo mã này một cách tường minh giúp kiểm soát thay đổi cấu trúc lớp. Tuy nhiên, giữ nguyên serialVersionUID không bảo đảm dữ liệu có cùng ý nghĩa nghiệp vụ hoặc mọi thay đổi đều an toàn. Ứng dụng vẫn cần thiết kế schema, chiến lược chuyển đổi và kiểm thử tương thích giữa các phiên bản đang chạy đồng thời.

## 1. Vì sao dữ liệu session tồn tại qua nhiều phiên bản ứng dụng?

Khi ứng dụng dùng Spring Session với Redis hoặc JDBC, dữ liệu phiên được lưu bên ngoài bộ nhớ của tiến trình. Một session có thể được tạo bởi instance A, sau đó được đọc bởi instance B. Trong rolling deployment, phiên bản cũ và phiên bản mới có thể cùng hoạt động trong một khoảng thời gian:

1. Instance cũ ghi một thuộc tính session vào Redis.
2. Một replica mới được triển khai và nhận request tiếp theo của người dùng.
3. Replica mới tải byte đã lưu và giải tuần tự hóa thành đối tượng Java.
4. Nếu lớp ở phiên bản mới không tương thích với object stream cũ, việc đọc có thể thất bại hoặc tạo ra giá trị không còn đúng về nghiệp vụ.

Điều này không chỉ xảy ra khi nâng cấp toàn bộ ứng dụng. Một session có thể sống lâu hơn một instance, một lần restart hoặc một đợt triển khai. Thời gian sống của dữ liệu session vì vậy tạo ra một hợp đồng tương thích giữa các phiên bản mã nguồn.

Spring Session không tự động chuyển đổi mọi đối tượng Java trong session khi lớp thay đổi. Repository lưu và tải dữ liệu theo serializer được cấu hình. Khả năng tương thích phụ thuộc serializer đó, kiểu dữ liệu được lưu và thay đổi của lớp.

## 2. Java Serialization và serialVersionUID

Một lớp muốn được Java native serialization xử lý thường triển khai java.io.Serializable:

~~~java
import java.io.Serializable;

public class UserSessionData implements Serializable {

    private static final long serialVersionUID = 1L;

    private String userId;
    private String displayName;
    private String locale;

    // Constructor, getter và setter.
}
~~~

Khi ghi đối tượng, Java Serialization lưu thông tin mô tả lớp cùng các trường được tuần tự hóa. Khi đọc, JVM so sánh serialVersionUID trong stream với serialVersionUID của lớp hiện tại.

- Nếu hai giá trị không khớp, việc giải tuần tự hóa thường thất bại với InvalidClassException.
- Nếu lớp không khai báo serialVersionUID, JVM tính một giá trị mặc định dựa trên cấu trúc lớp.
- Giá trị mặc định có thể thay đổi khi chỉnh sửa khai báo lớp, method, field hoặc các chi tiết cấu trúc khác, kể cả thay đổi tưởng như không ảnh hưởng dữ liệu.
- Khai báo serialVersionUID tường minh giúp tránh việc JVM tự tính lại mã phiên bản sau mỗi thay đổi cấu trúc.

Nên khai báo serialVersionUID trong mọi lớp Serializable được lưu vào session hoặc được tham chiếu từ một đối tượng session:

~~~java
private static final long serialVersionUID = 1L;
~~~

Đây là một giá trị do nhóm phát triển quản lý. Không thay đổi nó một cách máy móc ở mỗi lần build. Chỉ tăng hoặc thay đổi khi chủ động tạo một định dạng serialized mới không còn tương thích với định dạng cũ, đồng thời đã có kế hoạch xử lý dữ liệu cũ.

## 3. serialVersionUID không phải phiên bản nghiệp vụ

serialVersionUID chỉ tham gia kiểm tra tương thích của Java object stream. Nó không phải version của ứng dụng, không phải schema version có khả năng chuyển đổi dữ liệu và cũng không chứng minh hai lớp có cùng ý nghĩa nghiệp vụ.

Ví dụ, lớp cũ có trường:

~~~java
private int accessLevel;
~~~

Ở phiên bản mới, nhóm phát triển giữ nguyên serialVersionUID nhưng đổi ý nghĩa của accessLevel từ số nguyên cấp quyền sang mã phân loại khác. Java có thể vẫn đọc được stream, nhưng giá trị được diễn giải sai và có thể tạo ra lỗi phân quyền.

Một ví dụ khác: đổi tên trường từ userName sang displayName. Nếu giữ serialVersionUID, stream cũ không tự động ánh xạ trường userName sang displayName. Trường mới có thể nhận giá trị mặc định null, dù việc giải tuần tự hóa không báo InvalidClassException.

Vì vậy, có hai câu hỏi cần kiểm tra riêng:

1. **Tương thích kỹ thuật:** Java có thể đọc object stream cũ bằng lớp mới hay không?
2. **Tương thích ngữ nghĩa:** giá trị sau khi đọc có còn biểu diễn đúng trạng thái mà ứng dụng mong đợi hay không?

Chỉ kiểm tra serialVersionUID là chưa đủ để xác nhận dữ liệu session an toàn sau triển khai.

## 4. Những thay đổi lớp thường gặp

Java Serialization có một số quy tắc tương thích cho thay đổi field. Các quy tắc này áp dụng trong phạm vi native serialization và còn phụ thuộc lớp, kiểu trường, quan hệ kế thừa cùng các phương thức serialization tùy chỉnh.

| Thay đổi lớp | Hành vi thường gặp khi đọc stream cũ | Điều cần lưu ý |
| --- | --- | --- |
| Thêm trường instance mới | Trường mới nhận giá trị mặc định nếu stream cũ không có trường đó | Khởi tạo giá trị mặc định nghiệp vụ |
| Bỏ trường cũ | Dữ liệu của trường không còn được lớp mới sử dụng | Có thể bỏ qua dữ liệu cũ, nhưng cần kiểm tra logic phụ thuộc |
| Đổi tên trường | Trường mới không tự nhận giá trị của tên cũ | Cần migration hoặc giữ tương thích có chủ đích |
| Đổi kiểu trường | Có thể gây lỗi không tương thích | Thường cần chuyển đổi dữ liệu hoặc định dạng mới |
| Đổi serialVersionUID | Thường gây InvalidClassException khi đọc stream có UID cũ | Chỉ thay đổi khi có kế hoạch loại bỏ hoặc chuyển đổi dữ liệu cũ |
| Thay đổi lớp cha Serializable | Có thể ảnh hưởng cấu trúc stream | Kiểm tra toàn bộ cây kế thừa |
| Thêm đối tượng tham chiếu không Serializable | Ghi object graph có thể thất bại | Kiểm tra mọi đối tượng được tham chiếu |

Ví dụ thêm trường locale:

~~~java
public class UserSessionData implements Serializable {

    private static final long serialVersionUID = 1L;

    private String userId;
    private String displayName;
    private String locale;

    private void readObject(java.io.ObjectInputStream input)
            throws java.io.IOException, ClassNotFoundException {
        input.defaultReadObject();
        if (locale == null) {
            locale = "vi-VN";
        }
    }
}
~~~

Nếu object stream cũ chưa có trường locale, giá trị sau khi đọc thường là null đối với kiểu tham chiếu. readObject ở trên gán mặc định nghiệp vụ sau khi đọc các trường mặc định. Giá trị mặc định phải phù hợp với dữ liệu cũ; không chọn một giá trị có thể làm thay đổi quyền hoặc trạng thái giao dịch.

Các trường primitive nhận giá trị mặc định của kiểu tương ứng như 0 hoặc false. Những trường static và transient không được ghi như trạng thái instance thông thường. Không dùng transient cho dữ liệu cần được giữ giữa các request.

## 5. Đối tượng trong session là một object graph

Một thuộc tính session có thể tham chiếu đến nhiều đối tượng khác. Khi Java Serialization ghi đối tượng gốc, nó có thể cần ghi cả các đối tượng được tham chiếu trong object graph.

Ví dụ:

~~~java
public class CartSession implements Serializable {

    private static final long serialVersionUID = 1L;

    private String cartId;
    private List<CartItem> items;
}

public class CartItem implements Serializable {

    private static final long serialVersionUID = 1L;

    private String productId;
    private int quantity;
}
~~~

CartSession triển khai Serializable chưa đủ nếu CartItem hoặc một đối tượng lồng bên trong không tuần tự hóa được. Khi ghi, Java có thể ném NotSerializableException. Khi đọc, các lớp trong graph cũng cần có mặt và tương thích.

Trước khi lưu một object graph vào session, hãy kiểm tra:

- Mọi lớp cần tuần tự hóa đều triển khai Serializable nếu dùng native Java serialization.
- Mọi lớp đều có serialVersionUID tường minh và được quản lý có chủ đích.
- Không lưu connection, stream, thread, servlet request/response, EntityManager hoặc đối tượng gắn với vòng đời một instance.
- Không lưu proxy ORM hoặc entity graph lớn nếu không có chiến lược rõ ràng.
- Không lưu đối tượng chứa trạng thái nội bộ của framework nếu có thể lưu một DTO nhỏ hơn.

Session nên chứa dữ liệu nhỏ và ổn định như user ID, mã giỏ hàng, lựa chọn giao diện hoặc trạng thái quy trình tạm thời. Dữ liệu nghiệp vụ chính như đơn hàng và tồn kho nên nằm trong kho dữ liệu nghiệp vụ.

## 6. Quản lý serialVersionUID khi thay đổi lớp

Hãy xem mỗi lớp Serializable được lưu trong session là một phần của định dạng dữ liệu được chia sẻ giữa các instance.

Một quy trình thực tế:

1. Xác định các lớp có thể được lưu trực tiếp hoặc gián tiếp trong session.
2. Khai báo serialVersionUID tường minh cho từng lớp Serializable.
3. Lưu fixture serialized từ phiên bản hiện tại để dùng trong kiểm thử tương thích.
4. Khi thay đổi field, phân tích tác động đến dữ liệu cũ và dữ liệu mới.
5. Viết logic mặc định hoặc migration nếu cần.
6. Kiểm thử đọc dữ liệu cũ bằng mã mới và kiểm thử mã cũ đọc dữ liệu do mã mới ghi nếu rolling deployment có thể xảy ra.
7. Chỉ triển khai khi các phiên bản chạy đồng thời có thể trao đổi dữ liệu theo hợp đồng đã chọn.

Không tăng serialVersionUID chỉ để “đánh dấu phiên bản mới”. Nếu tăng UID, stream cũ thường không thể đọc bằng lớp mới. Điều này có thể khiến request đầu tiên sau deployment gặp lỗi khi tải session đang tồn tại.

Ngược lại, không giữ UID cũ một cách mù quáng khi thay đổi không tương thích. Nếu giữ UID nhưng thay đổi kiểu dữ liệu hoặc ý nghĩa field, việc đọc có thể thất bại hoặc âm thầm tạo trạng thái sai.

## 7. Tương thích hai chiều trong rolling deployment

Trong rolling deployment, phiên bản cũ và mới có thể cùng chạy và cùng truy cập Redis hoặc JDBC. Chỉ kiểm thử “mã mới đọc dữ liệu cũ” có thể chưa đủ.

Ví dụ:

- Phiên bản A cũ ghi một đối tượng UserSessionData.
- Phiên bản B mới đọc được đối tượng đó và thêm trường mới.
- B ghi lại session với trường mới.
- Một request tiếp theo được định tuyến về A.
- A có thể không hiểu dữ liệu mới hoặc có thể bỏ qua trường mới khi đọc rồi ghi lại.

Một số thay đổi tương thích theo hướng cũ sang mới nhưng không tương thích theo hướng mới sang cũ. Đây là lý do cần xem xét cả hai chiều:

| Dữ liệu được ghi bởi | Được đọc bởi | Câu hỏi cần trả lời |
| --- | --- | --- |
| Phiên bản cũ | Phiên bản mới | Lớp mới có đọc được session hiện có không? |
| Phiên bản mới | Phiên bản cũ | Lớp cũ có đọc được dữ liệu mà replica mới đã ghi không? |
| Phiên bản mới | Phiên bản mới | Các instance mới có dùng cùng định dạng và cấu hình serializer không? |

Nếu phiên bản cũ không thể đọc dữ liệu mới, có thể cần triển khai theo nhiều giai đoạn:

1. Triển khai phiên bản trung gian có thể đọc cả dữ liệu cũ lẫn dữ liệu mới nhưng vẫn ghi định dạng cũ.
2. Chờ toàn bộ replica cũ hơn được thay thế.
3. Bật ghi định dạng mới.
4. Chờ session cũ hết hạn hoặc chuyển đổi dữ liệu cũ.
5. Loại bỏ nhánh tương thích cũ trong một lần triển khai sau.

Đây là một dạng expand-and-contract. Nó giảm nguy cơ một replica cũ nhận dữ liệu mà nó không thể đọc.

## 8. Xử lý khi đổi tên hoặc đổi kiểu field

Đổi tên field không tự động đổi tên dữ liệu trong object stream. Nếu cần đổi từ name sang displayName, có thể giữ field cũ trong một giai đoạn chuyển tiếp:

~~~java
public class UserSessionData implements Serializable {

    private static final long serialVersionUID = 1L;

    // Trường cũ giữ lại để đọc dữ liệu đã lưu từ phiên bản trước.
    @Deprecated
    private String name;

    private String displayName;

    private void readObject(java.io.ObjectInputStream input)
            throws java.io.IOException, ClassNotFoundException {
        input.defaultReadObject();
        if (displayName == null) {
            displayName = name;
        }
    }
}
~~~

Ví dụ này minh họa việc đọc dữ liệu cũ. Cần đánh giá chiều ghi và khả năng tương thích với phiên bản cũ trước khi dùng trong rolling deployment. Phiên bản cũ có thể không nhận được giá trị mới nếu phiên bản mới chỉ ghi displayName. Nếu cần tương thích hai chiều, có thể phải tiếp tục ghi trường cũ trong thời gian chuyển tiếp hoặc dùng một định dạng DTO/version rõ ràng.

Khi đổi kiểu, ví dụ String thành UUID hoặc int thành một enum, không nên trông đợi Java tự chuyển đổi giá trị. Hãy viết migration rõ ràng hoặc giữ field cũ để đọc, chuyển đổi sang field mới rồi ghi lại theo phiên bản schema mới.

Không nên viết custom readObject quá phức tạp cho mọi thay đổi. Logic serialization tùy chỉnh khó kiểm thử và có thể trở thành một định dạng riêng cần duy trì lâu dài. Nếu cấu trúc session thay đổi thường xuyên, DTO có version hoặc serializer có schema rõ ràng thường dễ quản lý hơn.

## 9. serialVersionUID trong Spring Session Redis và JDBC

Spring Session lưu thuộc tính session bằng serializer của repository. Cần xác định serializer thực tế trước khi kết luận serialVersionUID có ảnh hưởng hay không.

- Nếu thuộc tính được ghi bằng Java native serialization, serialVersionUID của lớp Serializable tham gia vào quá trình đọc dữ liệu.
- Nếu ứng dụng dùng JSON, CBOR hoặc serializer khác, serialVersionUID Java không được dùng để xác định schema của định dạng đó.
- Nếu session chứa một đối tượng bao bọc có các đối tượng lồng nhau, mọi lớp trong object graph được native serialization xử lý đều có thể ảnh hưởng.

Với Redis, serializer có thể được cấu hình cho dữ liệu session. Một số cấu hình Spring Session Redis sử dụng JDK serialization; các ứng dụng cũng có thể cung cấp serializer khác. Với JDBC, cách chuyển đổi thuộc tính phụ thuộc phiên bản Spring Session và cấu hình serializer/conversion service của repository. Không giả định Redis và JDBC luôn dùng cùng một định dạng.

Ví dụ cấu hình Redis dùng serializer Jackson cho thuộc tính session:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

@Configuration
class SessionSerializationConfiguration {

    @Bean
    RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return new GenericJackson2JsonRedisSerializer();
    }
}
~~~

Bean có tên springSessionDefaultRedisSerializer được Spring Session Redis sử dụng ở các phiên bản hỗ trợ điểm cấu hình này. Cần xác minh tên bean và API với phiên bản Spring Session/Spring Data Redis trong dự án. JSON có thể giúp giảm phụ thuộc vào serialVersionUID, nhưng không tự động giải quyết tương thích schema: đổi tên field, đổi kiểu, thiếu thuộc tính hoặc thay đổi polymorphic type vẫn cần chính sách chuyển đổi.

Nếu dùng Jackson polymorphic typing để lưu nhiều kiểu đối tượng khác nhau, chỉ cho phép các kiểu cần thiết và tránh bật cơ chế type metadata rộng cho dữ liệu không tin cậy. Dữ liệu session có thể chứa thông tin xác thực; không biến serializer thành điểm giải tuần tự hóa tùy ý.

## 10. Chọn native serialization hay định dạng có schema

| Tiêu chí | Java native serialization | JSON/serializer có schema |
| --- | --- | --- |
| Phụ thuộc lớp Java | Cao | Có thể thấp hơn nếu dùng DTO và tên field ổn định |
| serialVersionUID | Có ý nghĩa trực tiếp | Không áp dụng cho định dạng JSON |
| Đọc dữ liệu ngoài Java | Khó hơn | Thường thuận tiện hơn |
| Thay đổi field | Theo quy tắc Java Serialization | Cần quy tắc schema và migration riêng |
| Kích thước/tốc độ | Tùy object graph và implementation | Tùy serializer, cấu trúc và dữ liệu |
| Rủi ro giải tuần tự hóa | Có rủi ro gadget khi dữ liệu không tin cậy | Cũng cần kiểm soát type binding và dữ liệu đầu vào |

Native serialization tiện cho object graph Java nhưng làm dữ liệu phụ thuộc mạnh vào lớp và phiên bản. JSON thường dễ quan sát, kiểm thử và tiến hóa hơn khi dùng DTO đơn giản. Không có lựa chọn nào tự động an toàn; phải kiểm tra tính tương thích, hiệu năng và chính sách bảo mật.

Với session phân tán, ưu tiên DTO nhỏ, ít thay đổi và có schema rõ ràng. Tránh lưu đối tượng framework, entity ORM hoặc các lớp có cấu trúc thay đổi thường xuyên.

## 11. Kiểm thử dữ liệu đã lưu từ phiên bản cũ

Kiểm thử tương thích cần dùng dữ liệu serialized thật được tạo bởi phiên bản cũ. Chỉ tạo object mới bằng lớp hiện tại rồi serialize và deserialize lại không kiểm chứng khả năng đọc dữ liệu từ release trước.

Một cách tổ chức:

1. Ở phiên bản A, tạo một session fixture với các thuộc tính đại diện.
2. Lưu các byte serialized hoặc một bản ghi test Redis/JDBC được bảo vệ trong thư mục fixture của bộ kiểm thử.
3. Ở phiên bản B, đọc fixture bằng serializer đang dùng.
4. Xác nhận các trường cũ giữ đúng giá trị và các trường mới nhận mặc định nghiệp vụ.
5. Nếu rolling deployment cần hỗ trợ hai chiều, tạo fixture từ B và thử đọc bằng A.
6. Kiểm tra lỗi với UID không khớp, kiểu field thay đổi và object graph thiếu lớp.

Có thể dùng công cụ serialver để xem serialVersionUID được tính cho một lớp:

~~~bash
serialver -classpath target/classes com.example.session.UserSessionData
~~~

Khi lớp đã khai báo UID tường minh, công cụ sẽ hiển thị giá trị đó. Nếu không khai báo, giá trị mặc định được tính từ lớp và có thể thay đổi khi cấu trúc thay đổi. Nên xem serialver như công cụ chẩn đoán; giải pháp lâu dài là khai báo UID trong mã nguồn và kiểm thử fixture.

Ví dụ kiểm thử tối giản với ObjectOutputStream và ObjectInputStream:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

final class SerializationFixtureCodec {

    static byte[] serialize(Object value) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(value);
        }
        return bytes.toByteArray();
    }

    static Object deserialize(byte[] bytes) throws Exception {
        try (ObjectInputStream input =
                new ObjectInputStream(new ByteArrayInputStream(bytes))) {
            return input.readObject();
        }
    }
}
~~~

Đoạn mã trên chỉ minh họa API Java. Bộ kiểm thử tương thích thực tế phải đọc byte fixture đã được tạo bởi phiên bản cũ, không phải chỉ gọi serialize rồi deserialize trong cùng một lần chạy.

## 12. Kiểm thử rolling deployment với Spring Session

Ngoài unit test cho lớp Serializable, cần kiểm thử tích hợp trên repository thực:

- Khởi chạy phiên bản cũ và tạo session chứa DTO được lưu.
- Khởi chạy phiên bản mới kết nối cùng Redis hoặc database thử nghiệm.
- Gửi request mang cùng cookie đến phiên bản mới và xác nhận đọc được thuộc tính.
- Cập nhật session ở phiên bản mới rồi gửi request tiếp theo đến phiên bản cũ nếu kiến trúc cho phép hai phiên bản chạy song song.
- Xác nhận session hết hạn và đăng xuất vẫn hoạt động sau quá trình chuyển đổi.
- Kiểm tra dữ liệu trong repository sau khi đổi serializer hoặc namespace.

Không dùng repository production để kiểm thử migration. Dùng Redis/database riêng, dữ liệu giả và cookie test không có quyền truy cập hệ thống thật.

Khi thay serializer, cần xem dữ liệu session cũ có thể được đọc bởi serializer mới hay không. Chuyển từ JDK serialization sang JSON thường không thể chỉ đổi bean serializer rồi kỳ vọng dữ liệu cũ tự đọc được. Có thể cần:

1. Chờ session cũ hết hạn trước khi chuyển.
2. Dùng namespace hoặc repository mới và yêu cầu người dùng tạo session mới.
3. Viết bộ chuyển đổi đọc định dạng cũ, ghi định dạng mới theo quy trình có kiểm soát.

Không đổi serializer trong khi session còn hiệu lực mà chưa xác định cách xử lý dữ liệu đã ghi.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi hoặc biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| InvalidClassException | serialVersionUID của stream và lớp hiện tại không khớp | Xác định phiên bản tạo dữ liệu; dùng migration hoặc chính sách hết hạn dữ liệu cũ |
| NotSerializableException | Một đối tượng trong object graph không Serializable | Thay bằng DTO đơn giản hoặc loại bỏ trường không cần lưu |
| Trường mới luôn null hoặc 0 | Stream cũ không có trường đó | Gán mặc định nghiệp vụ trong logic đọc hoặc migration |
| Trường đổi tên mất giá trị | Java không tự ánh xạ tên field cũ sang tên mới | Giữ field tương thích hoặc viết chuyển đổi rõ ràng |
| Một replica đọc được, replica khác lỗi | Các replica dùng lớp, dependency hoặc serializer khác nhau | Đồng bộ artifact, cấu hình và phiên bản serializer |
| Session mất sau đổi serializer | Dữ liệu cũ không cùng định dạng với serializer mới | Giữ reader tương thích hoặc chuyển đổi/cho hết hạn có kế hoạch |
| Dữ liệu đọc được nhưng nghiệp vụ sai | UID giữ nguyên nhưng ý nghĩa field đã đổi | Kiểm thử ngữ nghĩa, migration và xác thực giá trị sau khi đọc |

Khi gặp lỗi giải tuần tự hóa, không xóa toàn bộ kho session ngay lập tức. Trước tiên xác định phạm vi release, lớp và serializer gây lỗi. Nếu chỉ một loại thuộc tính bị ảnh hưởng, có thể bỏ thuộc tính lỗi hoặc yêu cầu người dùng đăng nhập lại theo chính sách. Việc xóa toàn bộ session có thể khiến mọi người dùng bị đăng xuất và che khuất nguyên nhân gốc.

## 14. Bảo mật khi giải tuần tự hóa

Java native deserialization có rủi ro nếu ứng dụng giải tuần tự hóa byte do nguồn không tin cậy kiểm soát. Một object stream có thể kích hoạt hành vi trong các lớp nằm trên classpath thông qua cơ chế deserialization. Nếu kẻ tấn công có thể ghi dữ liệu tùy ý vào kho session hoặc vào đường dữ liệu được giải tuần tự hóa, hậu quả có thể nghiêm trọng.

Các nguyên tắc bảo vệ:

- Chỉ cho phép ứng dụng truy cập Redis/database session bằng credential riêng và quyền tối thiểu.
- Không giải tuần tự hóa dữ liệu tùy ý từ client hoặc nguồn bên ngoài.
- Giữ thư viện và framework được cập nhật; loại bỏ dependency không cần thiết.
- Cân nhắc Java ObjectInputFilter hoặc giới hạn kiểu được phép trong đường giải tuần tự hóa mà ứng dụng kiểm soát.
- Dùng DTO nhỏ, định dạng rõ ràng và allowlist kiểu nếu serializer hỗ trợ.
- Không lưu password, token dài hạn hoặc bí mật không cần thiết trong session.
- Bảo vệ backup và log; serialized session có thể chứa thông tin xác thực và dữ liệu cá nhân.

serialVersionUID không phải cơ chế bảo mật và không ngăn object stream độc hại. Nó chỉ là một phần kiểm tra tương thích lớp.

## 15. Quy trình đề xuất trước khi phát hành

- [ ] Xác định serializer thực tế của Spring Session Redis/JDBC.
- [ ] Liệt kê các lớp Serializable có thể nằm trong session object graph.
- [ ] Khai báo serialVersionUID tường minh cho các lớp native-serialized.
- [ ] Phân tích thêm/bỏ/đổi tên/đổi kiểu field và thay đổi lớp cha.
- [ ] Kiểm tra cả tương thích kỹ thuật lẫn ý nghĩa nghiệp vụ sau khi đọc.
- [ ] Lưu fixture từ release trước và chạy kiểm thử đọc dữ liệu cũ.
- [ ] Kiểm thử hai chiều nếu phiên bản cũ và mới cùng chạy.
- [ ] Có kế hoạch migration hoặc hết hạn session khi đổi định dạng.
- [ ] Không thay serializer khi chưa xử lý dữ liệu hiện có.
- [ ] Bảo vệ đường giải tuần tự hóa và kho session khỏi dữ liệu không tin cậy.

serialVersionUID giúp Java nhận biết phiên bản của lớp Serializable trong object stream, nhưng tương thích session là vấn đề lớn hơn một con số. Spring Session có thể lưu dữ liệu lâu hơn vòng đời của một instance, nên mọi thay đổi lớp hoặc serializer cần được đánh giá trong bối cảnh nhiều phiên bản cùng truy cập repository. Khai báo UID tường minh, dùng DTO ổn định, kiểm thử fixture cũ và triển khai migration theo giai đoạn sẽ giảm nguy cơ lỗi giải tuần tự hóa và dữ liệu session sai nghĩa sau nâng cấp.
