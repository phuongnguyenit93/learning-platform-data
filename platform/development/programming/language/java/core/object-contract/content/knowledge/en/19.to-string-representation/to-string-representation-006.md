# Phân biệt toString() với tuần tự hóa và định dạng trao đổi ổn định

## 1. Cùng một đối tượng, ba mục đích khác nhau

Trong Java, việc biến một đối tượng thành chuỗi để **người đọc hiểu**, chuyển trạng thái đối tượng thành dữ liệu để **khôi phục**, và tạo một định dạng để **nhiều thành phần hệ thống trao đổi lâu dài** là ba nhu cầu khác nhau.

1. **`toString()`** tạo biểu diễn văn bản phục vụ quan sát, gỡ lỗi, ghi log hoặc trình bày giản lược. Mặc định, nội dung và cách trình bày là quyết định của lớp; hợp đồng `Object.toString()` không bắt buộc biểu diễn đó phải đọc ngược được.
2. **Tuần tự hóa (serialization)** chuyển thông tin đối tượng thành biểu diễn có thể lưu hoặc truyền và, nếu có quy trình tương ứng, dựng lại trạng thái. Java có cơ chế riêng là `ObjectOutputStream`/`ObjectInputStream`, nhưng đây chỉ là **một** kiểu serialization. JSON, XML, Protobuf và các định dạng nhị phân có schema cũng thuộc nhóm biểu diễn dữ liệu có cấu trúc.
3. **Định dạng trao đổi ổn định (stable interchange format)** cần một hợp đồng dữ liệu rõ ràng: trường nào tồn tại, kiểu dữ liệu gì, mã hóa ký tự ra sao, quy tắc `null`, thứ tự/độ chính xác, cách xử lý phiên bản, và mức tương thích khi nâng cấp. Một định dạng ổn định thường được tạo bởi bộ tuần tự hóa và bộ phân tích dữ liệu có cấu trúc, không lấy từ `toString()` một cách tùy tiện.

Hai trục này liên quan nhưng không đồng nghĩa: *serialization* mô tả hoạt động chuyển dữ liệu sang biểu diễn khác; *ổn định để trao đổi* là một thuộc tính được thiết kế và duy trì của **định dạng cùng hợp đồng xử lý nó**.

| Tiêu chí | `toString()` | Java object serialization | Định dạng trao đổi có hợp đồng |
| --- | --- | --- | --- |
| Mục đích chính | Hiển thị, chẩn đoán, gỡ lỗi | Ghi/đọc đồ thị đối tượng Java theo cơ chế JDK | Giao tiếp API, lưu bền vững, kết nối nhiều hệ thống |
| Định dạng bắt buộc | Không có schema chung | Luồng nhị phân theo cơ chế Java serialization | Schema, phiên bản, quy tắc mã hóa được công bố |
| Có thể đọc ngược mặc định | Không | Có trong điều kiện lớp tương thích | Có khi tồn tại decoder/parser tương ứng |
| Dùng với ngôn ngữ khác | Không bảo đảm | Không phải giao thức trung lập ngôn ngữ | Có thể, nếu dùng định dạng và schema được các bên hỗ trợ |
| Ổn định khi sửa code | Không được bảo đảm | Phụ thuộc quy tắc tương thích và phiên bản lớp | Phụ thuộc quản trị schema và cam kết tương thích |
| Dùng cho dữ liệu không tin cậy | Không nên coi là định dạng nhập liệu | Không nên giải tuần tự hóa luồng không tin cậy | Cần parser, kiểm tra schema, giới hạn kích thước và xác thực phù hợp |

**Nguyên tắc quan trọng:** Chuỗi nhìn “giống JSON” hay “giống một dòng dữ liệu” không tự biến `toString()` thành API serialization. Chính hợp đồng được công bố và kiểm chứng mới quyết định các hệ thống có thể dựa vào định dạng đó hay không.

## 2. toString() thực sự hứa điều gì?

`toString()` là một phương thức của `java.lang.Object`. Khi chưa ghi đè, cách biểu diễn thường gặp là tên lớp, dấu `@` và mã băm ở dạng hexadecimal. Vì `Object.toString()` dựa trên phương thức `hashCode()`, phần sau dấu `@` **không được xem là định danh vĩnh viễn, duy nhất hoặc địa chỉ bộ nhớ**. Lớp có thể ghi đè `hashCode()`; mã băm cũng có thể trùng nhau.

Một lớp có thể ghi đè `toString()` để người phát triển đọc được các thuộc tính hữu ích:

~~~java
@Override
public String toString() {
    return "Order{id=" + id + ", quantity=" + quantity + "}";
}
~~~

Đây là **đoạn phương thức minh họa đặt trong lớp có các trường tương ứng**, không phải một chương trình độc lập. Biểu diễn vừa đủ rõ cho người đọc, nhưng nó chưa nói có cơ chế escape nào khi `id` chứa ký tự `}`, dấu phẩy hoặc xuống dòng. Nó cũng chưa định nghĩa cách diễn giải `null`, số rất lớn, thời gian, Unicode hay phiên bản dữ liệu.

Các thay đổi hoàn toàn hợp lý đối với chuỗi gỡ lỗi, chẳng hạn đổi tên trường từ `quantity` thành `qty`, thêm dấu ngoặc kép, hoặc ẩn một trường nhạy cảm, có thể phá chương trình đang lén tách chuỗi `toString()` bằng biểu thức chính quy.

Dùng `toString()` đúng chỗ:

- Khi cần nhìn nhanh giá trị trong debugger, log hoặc thông báo chẩn đoán.
- Khi biểu diễn hữu ích cho con người mà **không cam kết khả năng parse**.
- Khi có thể thay đổi cách trình bày theo yêu cầu bảo mật, trải nghiệm hoặc hỗ trợ kỹ thuật.

Không nên in mặc định mật khẩu, token, khóa bí mật, số định danh nhạy cảm hoặc nội dung riêng tư trong `toString()`: đối tượng có thể bị đưa vào log tự động. Mặt khác, nếu chuỗi này tiếp nhận dữ liệu từ bên ngoài, ký tự xuống dòng và dấu điều khiển có thể làm nhiễu log; cân nhắc escape, lược bỏ hoặc che trường phù hợp.

Lớp `record` trong Java sinh sẵn `toString()`, nhưng **hình thức chuỗi sinh tự động cũng không phải schema trao đổi lâu dài**. Việc dựa vào mẫu chuỗi ấy để lưu trạng thái hoặc giao tiếp giữa dịch vụ khiến cấu trúc chương trình nội bộ vô tình trở thành hợp đồng công khai.

## 3. Tuần tự hóa Java có giống toString() không?

Không. Cơ chế **Java object serialization** sử dụng giao diện `Serializable` và các lớp như `ObjectOutputStream`/`ObjectInputStream` để ghi và đọc luồng dữ liệu của các đối tượng được hỗ trợ. Đây là luồng nhị phân có định dạng riêng, không phải kết quả của `toString()`.

Ví dụ một đối tượng có:

~~~text
id = "A|B"
quantity = 3
~~~

Biểu diễn cho người đọc có thể là:

~~~text
Order{id=A|B, quantity=3}
~~~

Trong khi luồng của `ObjectOutputStream` chứa các thông tin serialization khác để Java có thể tái lập đối tượng, và không có lý do gì phải giống chuỗi trên. Số byte cụ thể phụ thuộc loại đối tượng, cấu trúc và dạng luồng; không nên dựa vào việc in các byte ra văn bản.

### serialVersionUID và tương thích

Với các lớp `Serializable` thông thường, `serialVersionUID` giúp xác định phiên bản lớp liên quan tới việc đọc luồng cũ. Khai báo mã phiên bản phù hợp có thể hỗ trợ một số thay đổi lớp tương thích, nhưng **không bảo đảm mọi lần sửa lớp đều đọc lại được dữ liệu trước đó**. Các trường mới/bị xóa, thay đổi phân cấp, kiểu trường, cơ chế khởi tạo, bất biến và quy tắc tùy biến đều cần được xem xét. Serialization của record có một số quy tắc đặc thù, nhưng vẫn không thay thế việc thiết kế schema bên ngoài.

Java object serialization phù hợp với một số trường hợp nội bộ có kiểm soát và nhu cầu tương thích đã biết. Không nên chọn nó mặc định làm giao thức công khai giữa nhiều ngôn ngữ, lưu cấu trúc dữ liệu nghiệp vụ dài hạn hoặc xử lý luồng từ nguồn không đáng tin cậy.

**Lưu ý an toàn:** Giải tuần tự hóa đối tượng Java từ dữ liệu không tin cậy có thể nguy hiểm, do cơ chế dựng đồ thị đối tượng và hành vi của các lớp có trên classpath. Tránh `ObjectInputStream` trên đầu vào tùy ý của người dùng; đối với đầu vào có kiểm soát vẫn cần giới hạn lớp/độ sâu/kích thước thích hợp và thiết kế nguồn tin cậy. Không đánh đồng việc một tệp “đọc lại được” với việc nó là một giao thức trao đổi phù hợp.

## 4. Định dạng trao đổi ổn định cần quy tắc nào?

“Ổn định” không có nghĩa là không được thay đổi bao giờ. Nó nghĩa là người đọc và người ghi **biết chính xác những gì được cam kết**, và các thay đổi được đưa ra theo chính sách tương thích có thể kiểm thử.

Ít nhất cần quyết định:

1. **Schema và tên trường:** Thực thể, trường bắt buộc/tùy chọn, kiểu, miền giá trị và cách phân biệt dữ liệu không tồn tại với `null`.
2. **Phiên bản:** Một mã phiên bản trong nội dung hoặc thông tin giao thức để nhận diện định dạng, cách chấp nhận các phiên bản cũ và cách từ chối phiên bản không hỗ trợ.
3. **Mã hóa:** UTF-8 hay một encoding khác; ký tự phân cách, escape, nhị phân, Unicode, độ dài và giới hạn kích thước.
4. **Giá trị có cấu trúc:** Quy tắc với số nguyên, số thập phân, ký hiệu thời gian, timezone, enum, danh sách và cấu trúc lồng nhau. Ví dụ thời điểm thời gian tuyệt đối và ngày cục bộ có ngữ nghĩa khác nhau.
5. **Ổn định khi thay đổi ứng dụng:** Thêm trường tùy chọn, thay đổi tên, bỏ trường và đổi kiểu cần chính sách migration/đọc dữ liệu cũ.
6. **Xác thực và báo lỗi:** Parser phải từ chối dữ liệu hỏng hoặc vượt giới hạn, không ngầm chấp nhận trạng thái sai rồi tạo ra đối tượng không hợp lệ.
7. **Khả năng tương tác:** Các phía phải thống nhất quy tắc canonical nếu cần chữ ký, hash nội dung hoặc so sánh byte; chỉ dùng JSON không tự bảo đảm thứ tự thuộc tính hay cách biểu diễn số.
8. **Kiểm thử:** Giữ bộ dữ liệu mẫu (*golden files*), round-trip, kiểm thử đọc phiên bản cũ và trường hợp thiếu, sai kiểu hoặc chứa ký tự đặc biệt.

Đối với API thực tế, thường nên chọn định dạng có thư viện và tiêu chuẩn được dùng rộng rãi như JSON có schema và parser đáng tin, hoặc Protobuf khi có nhu cầu nhị phân và schema tiến hóa được. Việc tự nghĩ một chuỗi phân tách bằng dấu `|` chỉ phù hợp ví dụ nhỏ khi hai phía cùng kiểm soát đầy đủ định dạng; nếu không quy định escape thì dữ liệu đầu vào có ký tự `|` sẽ phá cách tách trường.

## 5. Ví dụ Java 17: cùng một Order ở ba biểu diễn

Chương trình dưới đây dùng một record `Order`, ghi đè `toString()` để dễ xem; định nghĩa **giao thức văn bản v1 minh họa** với định dạng `1|idBase64Url|quantity`; đồng thời cho thấy serialization nhị phân Java có thể dựng lại một đối tượng cùng giá trị từ luồng **nội bộ, đáng tin cậy**.

Vì `id` được encode bằng Base64 URL-safe không padding trên byte UTF-8, dữ liệu `"A|B"` không gây nhầm lẫn với dấu `|` ngăn các trường. `quantity` luôn được ghi ở dạng thập phân của `int`; parser kiểm tra phiên bản, số trường và quy tắc constructor. Giao thức v1 này là **ví dụ giảng dạy**, chưa phải chuẩn sẵn sàng dùng cho dữ liệu công khai nếu thiếu giới hạn kích thước, chiến lược tiến hóa và kiểm thử tương thích.

Tạo tệp **ToStringAndSerializationDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Objects;

public class ToStringAndSerializationDemo {
    record Order(String id, int quantity) implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        Order {
            Objects.requireNonNull(id, "id");
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity < 0");
            }
        }

        @Override
        public String toString() {
            return "Order{id=" + id + ", quantity=" + quantity + "}";
        }
    }

    static String encodeWireV1(Order order) {
        String encodedId = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(order.id().getBytes(StandardCharsets.UTF_8));
        return "1|" + encodedId + "|" + order.quantity();
    }

    static Order decodeWireV1(String wire) {
        String[] parts = wire.split("[|]", -1);
        if (parts.length != 3 || !parts[0].equals("1")) {
            throw new IllegalArgumentException("Unsupported wire format");
        }

        byte[] idBytes = Base64.getUrlDecoder().decode(parts[1]);
        String id = new String(idBytes, StandardCharsets.UTF_8);
        int quantity = Integer.parseInt(parts[2]);
        return new Order(id, quantity);
    }

    static byte[] writeJavaObject(Order order) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(bytes)) {
            output.writeObject(order);
        }
        return bytes.toByteArray();
    }

    static Order readTrustedJavaObject(byte[] bytes) throws Exception {
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            return (Order) input.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Order original = new Order("A|B", 3);

        String display = original.toString();
        String wire = encodeWireV1(original);
        Order fromWire = decodeWireV1(wire);

        System.out.println("display: " + display);
        System.out.println("wire: " + wire);
        System.out.println("wire round-trip equal: "
                + original.equals(fromWire));
        System.out.println("display equals wire: "
                + display.equals(wire));

        byte[] javaBytes = writeJavaObject(original);
        Order fromJavaBytes = readTrustedJavaObject(javaBytes);
        System.out.println("Java stream has bytes: "
                + (javaBytes.length > 0));
        System.out.println("Java object round-trip equal: "
                + original.equals(fromJavaBytes));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac ToStringAndSerializationDemo.java
java ToStringAndSerializationDemo
~~~

Kết quả dự kiến:

~~~text
display: Order{id=A|B, quantity=3}
wire: 1|QXxC|3
wire round-trip equal: true
display equals wire: false
Java stream has bytes: true
Java object round-trip equal: true
~~~

**Giải thích:**

- `display` phục vụ con người. Nếu ngày mai đổi thành `Order(A|B, 3)` thì ý nghĩa của đối tượng không đổi nhưng một trình phân tích phụ thuộc chuỗi cũ có thể hỏng.
- `wire` là một biểu diễn có cấu trúc được xác định tường minh. Chuỗi `A|B` được mã hóa thành `QXxC` trong Base64 URL-safe; khi đọc, parser có thể khôi phục chính xác `id` và `quantity` theo giao thức v1.
- `wire round-trip equal: true` xác nhận đối tượng được dựng lại có các thành phần tương đương với đối tượng ban đầu. **Round-trip đúng trong một phiên bản không tự chứng minh định dạng tương thích giữa các phiên bản khác nhau**.
- Java object stream tạo byte nhị phân và đọc lại một bản `Order` tương đương. Quá trình không gọi `toString()` để quyết định nội dung cần lưu.
- Việc record tự sinh `equals` theo các thành phần giúp kiểm tra nội dung sau round-trip. Biểu diễn `toString()`, định dạng wire và Java object stream là ba hợp đồng khác nhau.

Trong ví dụ, `readTrustedJavaObject` được đặt tên có chữ “Trusted” vì nó đọc lại byte do chính chương trình vừa tạo ra. **Không mở rộng phương thức đó thành API nhận byte tùy ý từ mạng hoặc người dùng.** Một ứng dụng thực tế cần kiểm soát nguồn dữ liệu, schema, validation, giới hạn tài nguyên và cách xử lý lỗi theo ranh giới bảo mật.

Ngoài ra, parser ví dụ biến byte Base64 thành `String` UTF-8 bằng constructor mặc định; trong dữ liệu sản xuất có yêu cầu nghiêm ngặt, cần quyết định rõ phải **từ chối** byte UTF-8 không hợp lệ thay vì chấp nhận chuỗi được thay ký tự, và tránh dữ liệu kích thước quá lớn. Trường hợp này càng cho thấy “định dạng ổn định” phải gồm cả quy tắc lỗi và giới hạn đầu vào.

## 6. Vì sao không nên lưu kết quả toString vào cơ sở dữ liệu như dữ liệu chính?

Giả sử phiên bản đầu lưu:

~~~text
Customer{id=42, name=Lan}
~~~

Một phiên bản sau đổi cách hiển thị:

~~~text
Customer #42 — Lan
~~~

Nếu dữ liệu được lưu chỉ để **đọc log**, khác biệt này là bình thường. Nhưng nếu một quy trình nhập dữ liệu vẫn tìm chuỗi `"id="` hoặc dấu phẩy để khôi phục `Customer`, quy trình đó sẽ không còn đọc được dữ liệu được viết bằng phiên bản mới.

Ngay cả khi không đổi format cố ý, cách biểu diễn chuỗi cũng có thể mơ hồ: tên khách hàng chứa dấu phẩy, dấu ngoặc, dấu bằng hoặc ký tự xuống dòng; trường `null` có thể bị in thành chữ `"null"` khiến không phân biệt được với chuỗi thật có giá trị đó. Với số và ngày tháng, khác biệt locale/timezone cũng có thể tạo ra nhiều văn bản cho cùng giá trị logic.

Đối với dữ liệu cần lưu/đọc sau nhiều lần triển khai ứng dụng, hãy lưu các cột có kiểu rõ ràng hoặc sử dụng định dạng cấu trúc với serializer/parser chính thức. Không nên dùng `toString()` như giao thức lưu trữ chỉ vì biểu diễn hiện tại dễ đọc.

## 7. “JSON từ toString()” có đủ để ổn định không?

Một cách triển khai dễ mắc lỗi:

~~~java
@Override
public String toString() {
    return "{\"id\":\"" + id + "\"}";
}
~~~

Đây là **đoạn minh họa lỗi**, không phải chương trình độc lập. Nếu `id` chứa dấu `"`, dấu `\`, newline hoặc ký tự điều khiển, kết quả có thể không còn là JSON hợp lệ hoặc mang ý nghĩa khác với giá trị ban đầu. Cách ghép chuỗi cũng dễ bỏ qua giá trị `null`, số thập phân và đối tượng lồng nhau.

Ngay cả khi có serializer JSON chuẩn và tạo được cú pháp JSON hợp lệ, tính **ổn định** vẫn phụ thuộc vào schema: trường nào được thêm, loại bỏ, đổi tên; cách mã hóa thời gian; khách hàng cũ xử lý trường không biết như thế nào; phiên bản API được quản lý ra sao. Nếu cần so sánh từng byte hoặc chữ ký số, còn cần quy định cách chuẩn hóa (canonicalization) thay vì giả định hai đối tượng JSON tương đương luôn được serialize ra chuỗi byte giống nhau.

Vì vậy, cần tách hai trách nhiệm: `toString()` phục vụ quan sát; **serializer và schema** tạo dữ liệu cho giao tiếp/lưu bền vững. Nếu muốn log một đoạn JSON, hãy coi đó là **structured logging** với thư viện hỗ trợ và chính sách bảo mật phù hợp, không phải lý do biến `toString()` thành định dạng truyền dữ liệu.

## 8. Lỗi phổ biến và cách tránh

### Nhầm 1: “toString đã chứa mọi trường, vậy có thể parse ngược”

Không có yêu cầu rằng `toString()` phải hiển thị **đủ** trường hoặc mã hóa chúng không mơ hồ. Một lớp có thể cố ý ẩn mật khẩu, cắt bớt danh sách dài, làm tròn số hoặc dịch tên thuộc tính cho dễ đọc. Ngay cả chuỗi đủ trường hôm nay cũng có thể đổi ngày mai.

### Nhầm 2: “Serializable tự biến object thành JSON”

`Serializable` là dấu hiệu tham gia cơ chế object serialization của Java; nó **không tự quy định JSON**. Để trao đổi JSON, thường cần thư viện và định nghĩa mapping/schema tương ứng.

### Nhầm 3: “Thêm serialVersionUID là đủ để tương thích mọi bản phát hành”

`serialVersionUID` liên quan đến kiểm tra tương thích phiên bản của Java serialization, nhưng không thay thế việc xem xét cách tiến hóa lớp và dữ liệu. Nó không biến byte của Java object stream thành định dạng trung lập ngôn ngữ, cũng không bảo đảm cấu trúc đã thay đổi vẫn giữ cùng ngữ nghĩa.

### Nhầm 4: “Có round-trip thành công là đã tạo format ổn định”

`decode(encode(x))` thành công chỉ kiểm chứng một phần tính đúng đắn hiện tại. Độ ổn định dài hạn đòi hỏi kiểm thử qua phiên bản, schema, dữ liệu biên, giới hạn kích thước và chính sách bỏ trường/tăng version.

### Nhầm 5: “StringBuilder ghép trường nhanh nên phù hợp truyền dữ liệu”

Hiệu năng ghép chuỗi không quyết định tính đúng đắn của định dạng. Nếu thiếu escape và versioning, một ký tự phân cách trong dữ liệu đầu vào đủ làm hỏng bộ phân tích. Một định dạng tiêu chuẩn có thư viện hỗ trợ thường đáng tin cậy hơn tối ưu thủ công không có hợp đồng.

### Nhầm 6: “In đầy đủ object là vô hại”

`toString()` có thể vô tình đưa thông tin nhạy cảm vào log, dữ liệu giám sát, thông báo lỗi hoặc hệ thống bên thứ ba. Chỉ đưa các trường cần thiết cho mục đích quan sát; tránh lộ secret, token và nội dung riêng tư.

## 9. Cách chọn giải pháp trong dự án Java

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Xem đối tượng trong debugger và log | `toString()` ngắn, dễ hiểu, có che dữ liệu nhạy cảm |
| In giá trị một mảng phục vụ gỡ lỗi | `Arrays.toString`/`Arrays.deepToString`, chỉ dùng làm hiển thị |
| Lưu đối tượng theo schema để trao đổi API | JSON/Protobuf/XML hoặc format được quy định chính thức, với serializer và parser |
| Lưu dữ liệu nghiệp vụ trong CSDL | Cột có kiểu và ràng buộc, hoặc cột JSON có schema/versioning rõ ràng |
| Tạo thông điệp có thể tiêu thụ qua nhiều phiên bản | DTO/schema riêng, versioning, kiểm thử tương thích và validation |
| Lưu/đọc đồ thị đối tượng Java ở môi trường tin cậy và có kiểm soát | Chỉ cân nhắc Java serialization khi hiểu rõ tương thích và rủi ro; không dùng cho đầu vào không tin cậy |
| Dùng giá trị văn bản làm khóa, chữ ký hoặc cache có yêu cầu tái lập | Quy tắc canonical ổn định, không dựa vào `toString()` tùy ý |

Trước khi triển khai, hãy trả lời: ai là người tiêu thụ kết quả, họ có cần đọc ngược không, dữ liệu tồn tại bao lâu, có ngôn ngữ/hệ thống khác hay không, các phiên bản phần mềm có cần cùng đọc nó không, và mức tin cậy của đầu vào là gì. Từ đó chọn định dạng và phương thức thích hợp.

**Ghi nhớ:** `toString()` là **biểu diễn cho con người**, không phải mặc nhiên là serialization. Java serialization tạo **luồng đối tượng Java** có điều kiện tương thích và an toàn riêng. Một **định dạng trao đổi ổn định** cần schema, mã hóa, parser, versioning và chính sách tương thích rõ ràng. Hãy thiết kế đúng theo mục đích sử dụng, thay vì dùng lại chuỗi tiện xem làm hợp đồng dữ liệu lâu dài.