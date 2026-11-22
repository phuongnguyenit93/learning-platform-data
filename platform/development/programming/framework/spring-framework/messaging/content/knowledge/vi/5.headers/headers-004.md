# NativeMessageHeaderAccessor và header của giao thức bên ngoài

## 1. Mục tiêu

Một message trong Spring có payload và một tập header mô tả message. Khi message đi qua một giao thức bên ngoài như STOMP hoặc JMS, ngoài các metadata phục vụ xử lý nội bộ của Spring, message còn có những header thuộc chính giao thức đó. Spring cần giữ được các header này để có thể đọc, xử lý và chuyển tiếp chúng khi encode message ra giao thức.

NativeMessageHeaderAccessor là lớp nền dành cho trường hợp đó. Nó mở rộng MessageHeaderAccessor và quản lý riêng các header đến từ nguồn bên ngoài. Trong ứng dụng, ta thường dùng lớp con dành cho giao thức cụ thể, chẳng hạn StompHeaderAccessor hoặc JmsMessageHeaderAccessor, thay vì tự tạo NativeMessageHeaderAccessor trực tiếp.

Sau bài học, người đọc có thể:

- Phân biệt header chuẩn của Spring với native header của giao thức bên ngoài.
- Giải thích cấu trúc lưu trữ native header và lý do Spring tách chúng khỏi processing header.
- Đọc, thay thế, thêm và xóa native header bằng đúng API.
- Dùng StompHeaderAccessor để tạo và đọc message mang header STOMP.
- Hiểu cách header giao thức được ánh xạ sang các header chung như destination và content type.
- Sửa header của message hiện có mà không cố thay đổi trực tiếp MessageHeaders bất biến.
- Tránh làm mất metadata, tin nhầm dữ liệu bên ngoài hoặc đưa thông tin nhạy cảm vào header.

## 2. Header trong Spring Message

Một Spring Message có hai phần:

- **Payload** là dữ liệu chính, ví dụ một đối tượng Order, chuỗi JSON hoặc mảng byte.
- **Headers** là metadata mô tả message, ví dụ id, timestamp, content type, destination, correlation id hoặc thông tin giao thức.

Kiểu MessageHeaders là một Map có thể đọc. Bản thân map này được thiết kế bất biến sau khi message được tạo; không nên gọi put hoặc remove trực tiếp trên message.getHeaders(). Muốn thay đổi header, hãy dùng MessageHeaderAccessor hoặc một lớp con phù hợp rồi tạo message mới.

Không phải mọi header đều có cùng mục đích. Có thể chia thành hai nhóm:

| Nhóm | Mục đích | Ví dụ |
|---|---|---|
| Spring processing headers | Phục vụ xử lý, định tuyến hoặc điều phối bên trong Spring | id, timestamp, contentType, simpDestination, simpSessionId |
| Native protocol headers | Giữ tên và giá trị header theo định dạng của giao thức nguồn/đích | destination, receipt, subscription, x-trace-id trong STOMP |

Tên “native” ở đây có nghĩa là header nguyên bản của giao thức hoặc message source bên ngoài. Nó không có nghĩa là header của hệ điều hành hay dữ liệu đặc biệt của JVM.

Một header có thể được ánh xạ thành thuộc tính chung của Spring và đồng thời được biểu diễn trong native header map. Ví dụ với STOMP, destination và content-type là header giao thức; Spring cũng cung cấp các accessor chung để ứng dụng đọc destination và content type mà không cần tự phân tích chuỗi STOMP.

## 3. NativeMessageHeaderAccessor lưu dữ liệu như thế nào?

NativeMessageHeaderAccessor kế thừa MessageHeaderAccessor. Các header bên ngoài được lưu tách biệt trong một sub-map dưới key NativeMessageHeaderAccessor.NATIVE_HEADERS.

Cấu trúc logic có thể hình dung như sau:

~~~text
Message
├── payload
└── MessageHeaders
    ├── id
    ├── timestamp
    ├── contentType
    ├── simpDestination
    ├── simpSessionId
    └── nativeHeaders
        ├── destination -> ["/app/orders"]
        ├── content-type -> ["application/json"]
        └── x-trace-id -> ["trace-123"]
~~~

Native header map có kiểu Map<String, List<String>>. Tên header là String và mỗi tên có thể gắn với một danh sách giá trị. Cấu trúc nhiều giá trị giúp Spring biểu diễn các nguồn giao thức có header lặp hoặc nhiều giá trị. Tuy nhiên, việc một header có thể xuất hiện nhiều lần và ý nghĩa của các giá trị đó phụ thuộc đặc tả giao thức. Không tự giả định mọi giao thức đều xử lý header trùng giống nhau.

Các điểm quan trọng:

- Header chung của Spring có thể chứa Object; native header được biểu diễn bằng String.
- Native header được giữ trong một vùng riêng, tránh trộn metadata giao thức với metadata điều phối nội bộ.
- NativeMessageHeaderAccessor có constructor protected và được thiết kế để dùng gián tiếp qua lớp con theo giao thức.
- Phương thức getNativeHeaders() là protected để lớp con truy cập map nội bộ.
- Phương thức toNativeHeaderMap() trả về một bản sao của native header map, không phải map nội bộ để sửa trực tiếp.

Các lớp liên quan thường gặp:

| Lớp | Vai trò |
|---|---|
| MessageHeaderAccessor | Đọc và sửa header chung của Spring |
| NativeMessageHeaderAccessor | Bổ sung vùng lưu native header |
| SimpMessageHeaderAccessor | Cung cấp header chung cho simple messaging protocol như destination, message type, session |
| StompHeaderAccessor | Ánh xạ và quản lý header của STOMP |
| JmsMessageHeaderAccessor | Truy cập metadata JMS qua abstraction của Spring |

Với WebSocket/STOMP, quan hệ kế thừa là StompHeaderAccessor → SimpMessageHeaderAccessor → NativeMessageHeaderAccessor → MessageHeaderAccessor. Vì vậy StompHeaderAccessor vừa có các API chung cho Spring messaging, vừa có thể đọc/ghi native header của STOMP.

## 4. Các API chính của NativeMessageHeaderAccessor

| API | Ý nghĩa |
|---|---|
| containsNativeHeader(name) | Kiểm tra native header có tên đó hay không |
| getNativeHeader(name) | Lấy toàn bộ List<String> giá trị của header; trả null nếu không có |
| getFirstNativeHeader(name) | Lấy giá trị đầu tiên; trả null nếu không có |
| setNativeHeader(name, value) | Đặt một giá trị mới, thay thế các giá trị cũ của cùng tên |
| addNativeHeader(name, value) | Thêm một giá trị vào danh sách hiện tại |
| addNativeHeaders(headers) | Thêm các native header từ MultiValueMap |
| removeNativeHeader(name) | Xóa header và trả về các giá trị trước đó |
| toNativeHeaderMap() | Trả về bản sao Map<String, List<String>> |
| copyHeaders(map) | Sao chép header chung; nếu map có `NativeMessageHeaderAccessor.NATIVE_HEADERS`, chép native header values vào accessor và thay thế giá trị native cùng tên |
| copyHeadersIfAbsent(map) | Sao chép header chung nếu key chưa có; native header map chỉ được nạp khi accessor chưa có native map, không merge từng native key còn thiếu |

Lưu ý: `NativeMessageHeaderAccessor` override hai phương thức này để xử lý riêng key `NATIVE_HEADERS`. `copyHeaders` nạp các native header từ map và ghi đè giá trị native cùng tên. `copyHeadersIfAbsent` chỉ nạp toàn bộ native map khi accessor chưa có native map; nó không gộp riêng từng native key đang thiếu. Quy tắc này khác với cách đọc đơn giản từ mô tả chung của `MessageHeaderAccessor`.

Ví dụ thao tác trên accessor:

~~~java
accessor.setNativeHeader("x-trace-id", "trace-123");
accessor.addNativeHeader("x-label", "priority");

String traceId = accessor.getFirstNativeHeader("x-trace-id");
List<String> labels = accessor.getNativeHeader("x-label");

boolean hasReceipt = accessor.containsNativeHeader("receipt");
List<String> removed = accessor.removeNativeHeader("x-obsolete");
~~~

setNativeHeader thay thế giá trị cũ. addNativeHeader nối thêm giá trị vào danh sách. Chỉ dùng nhiều giá trị khi giao thức và adapter cho phép; nếu giao thức quy định chỉ dùng một giá trị hoặc có quy tắc chọn giá trị đầu tiên, phải tuân thủ quy tắc đó.

Không nên lấy map từ toNativeHeaderMap() rồi kỳ vọng sửa map sẽ cập nhật lại accessor. Đây là bản sao phục vụ đọc, kiểm tra hoặc chuyển đổi. Muốn thay đổi dữ liệu đang được quản lý, hãy gọi các phương thức set/add/remove trên accessor khi accessor còn mutable.

## 5. Phân biệt setHeader và setNativeHeader

Đây là điểm dễ nhầm nhất khi làm việc với giao thức bên ngoài.

- setHeader(name, value) đặt một header chung ở cấp MessageHeaders. Header này phục vụ ứng dụng hoặc pipeline Spring.
- setNativeHeader(name, value) đặt header vào vùng nativeHeaders để lớp tích hợp giao thức có thể sử dụng khi chuyển đổi message.

Ví dụ:

~~~java
accessor.setHeader("internalAuditId", "audit-42");
accessor.setNativeHeader("x-trace-id", "trace-123");
~~~

internalAuditId là metadata nội bộ. Nó không tự động trở thành một header trên wire của STOMP. x-trace-id được đặt trong vùng native để có thể được lớp xử lý STOMP chuyển thành header giao thức, nếu adapter/endpoint cho phép header đó.

Đừng đặt mọi dữ liệu vào native header chỉ vì muốn truyền đi. Dữ liệu dùng nội bộ như đối tượng Principal, channel hoặc trạng thái xử lý nên nằm ở header chung phù hợp. Ngược lại, nếu cần giữ một header nguyên bản của giao thức qua bước xử lý và gửi tiếp, hãy dùng native header hoặc API chuyên biệt của giao thức.

## 6. STOMP là ví dụ điển hình

STOMP là giao thức nhắn tin dạng frame. Một frame thường gồm command, các dòng header, dòng trống, body và ký tự kết thúc frame.

Ví dụ frame SEND:

~~~text
SEND
destination:/app/orders
content-type:application/json
x-trace-id:trace-123

{"orderId":42}
~~~

Trong Spring, frame STOMP được chuyển thành Message<?>. StompHeaderAccessor đảm nhiệm việc đọc và tạo các header STOMP.

Khi đọc frame:

- Header STOMP nguyên bản được lưu trong native header sub-map.
- Một số header chuẩn được ánh xạ thành processing header của Spring.
- Ứng dụng có thể dùng getDestination(), getContentType() hoặc getSessionId() thay vì tự đọc native map cho các thuộc tính đã được hỗ trợ.
- Header tùy biến như x-trace-id có thể đọc qua getFirstNativeHeader("x-trace-id").

Khi tạo message gửi ra:

- setDestination() cập nhật destination chung của Spring và native destination của STOMP.
- setContentType() cập nhật content type chung và giá trị native tương ứng.
- setNativeHeader() dùng cho header STOMP tùy biến.
- StompHeaderAccessor quản lý STOMP command và các bước chuẩn bị frame theo hướng client hoặc server khi cần.

Không phải mọi header trong MessageHeaders đều tự động được gửi lên STOMP frame. Việc chuyển đổi do accessor và tầng transport thực hiện theo các quy tắc mapping của giao thức.

## 7. Ví dụ Java 17: tạo và đọc native STOMP header

Ví dụ sau tạo một message Spring có command SEND, destination và một header tùy biến. Sau đó, chương trình wrap message bằng StompHeaderAccessor để đọc lại các giá trị. Ví dụ chỉ kiểm tra abstraction trong bộ nhớ, không cần khởi động WebSocket server hoặc STOMP broker.

### 7.1. Cấu trúc dự án

~~~text
native-header-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── NativeHeadersDemo.java
~~~

### 7.2. Dependency Maven

Tạo file pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>native-header-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

spring-messaging chứa Message, MessageHeaders, MessageBuilder và các accessor. Maven sẽ tự tải các dependency bắc cầu cần thiết.

### 7.3. Chương trình

Tạo file src/main/java/com/example/NativeHeadersDemo.java:

~~~java
package com.example;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;

public class NativeHeadersDemo {

    public static void main(String[] args) {
        StompHeaderAccessor outgoing =
            StompHeaderAccessor.create(StompCommand.SEND);

        outgoing.setDestination("/app/orders");
        outgoing.setNativeHeader("x-trace-id", "trace-123");

        Message<String> message = MessageBuilder.createMessage(
            "Order created",
            outgoing.getMessageHeaders()
        );

        StompHeaderAccessor received = StompHeaderAccessor.wrap(message);

        System.out.println("command=" + received.getCommand());
        System.out.println("destination=" + received.getDestination());
        System.out.println(
            "traceId=" + received.getFirstNativeHeader("x-trace-id")
        );
        System.out.println("payload=" + message.getPayload());
    }
}
~~~

Chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.NativeHeadersDemo
~~~

Kết quả:

~~~text
command=SEND
destination=/app/orders
traceId=trace-123
payload=Order created
~~~

Giải thích:

1. create(StompCommand.SEND) tạo accessor dành cho frame SEND.
2. setDestination() thiết lập destination mà Spring dùng để định tuyến và cập nhật native destination của STOMP.
3. setNativeHeader() thêm header tùy biến vào native header map.
4. getMessageHeaders() cung cấp header để MessageBuilder tạo message. Sau khi header được đóng gói, accessor mặc định không còn mutable.
5. wrap(message) tạo accessor từ message hiện có để đọc hoặc điều chỉnh header.
6. getFirstNativeHeader() lấy giá trị đầu tiên của header x-trace-id.

Ví dụ này xác minh việc lưu và truy cập metadata trong Spring Message. Để kiểm tra header thực sự đi qua mạng, cần một STOMP endpoint và một integration test gửi/nhận frame qua WebSocket hoặc TCP transport.

## 8. Đọc native header khi chỉ có Message

Trong một interceptor hoặc component xử lý message tổng quát, đôi khi ta chỉ có Message<?> chứ không có sẵn StompHeaderAccessor. Có thể dùng phương thức static của NativeMessageHeaderAccessor để lấy giá trị đầu tiên từ MessageHeaders:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.NativeMessageHeaderAccessor;

public String readTraceId(Message<?> message) {
    return NativeMessageHeaderAccessor.getFirstNativeHeader(
        "x-trace-id",
        message.getHeaders()
    );
}
~~~

Phương thức static này đọc vùng native header từ map header của message và trả về null nếu không tìm thấy tên header. Nếu cần thao tác nhiều header hoặc cần các API riêng của STOMP, hãy wrap message bằng StompHeaderAccessor.

Có thể kiểm tra toàn bộ native map bằng accessor:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
Map<String, List<String>> nativeHeaders = accessor.toNativeHeaderMap();

nativeHeaders.forEach((name, values) ->
    System.out.println(name + " = " + values)
);
~~~

Map trả về là bản sao. Đoạn code trên chỉ để quan sát, log hoặc chuyển đổi; không dùng nó làm cách sửa native header của message.

## 9. Sửa native header của message hiện có

MessageHeaders là bất biến sau khi message được tạo. Không làm như sau:

~~~java
message.getHeaders().put("x-trace-id", "trace-123");
~~~

Lệnh trên không phải cách hợp lệ để cập nhật message và có thể ném UnsupportedOperationException.

Hãy tạo accessor mới từ message rồi tạo một message mới:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
accessor.setNativeHeader("x-processed-by", "order-service");

Message<?> updated = MessageBuilder.createMessage(
    message.getPayload(),
    accessor.getMessageHeaders()
);
~~~

wrap(message) sao chép header hiện có sang accessor có thể sửa. Message gốc không bị thay đổi; updated là message mới mang header đã bổ sung. Khi gọi getMessageHeaders(), accessor mặc định được chuyển sang trạng thái immutable để tránh sửa header sau khi message đã được công bố cho các thành phần khác.

Nếu một pipeline cần chuyển accessor qua nhiều thành phần trước khi hoàn tất message, MessageHeaderAccessor có setLeaveMutable(true) và setImmutable(). Chỉ để header mutable trong phạm vi được kiểm soát; trước khi chia sẻ message qua thread hoặc component khác, hãy hoàn tất việc sửa và đóng băng header.

## 10. Mapping giữa native header và processing header

Native header và processing header có thể cùng mô tả một ý nghĩa nhưng phục vụ hai lớp khác nhau.

Với STOMP:

| STOMP header | Cách Spring thường cung cấp |
|---|---|
| destination | SimpMessageHeaderAccessor.getDestination() |
| content-type | MessageHeaderAccessor.getContentType() và StompHeaderAccessor |
| subscription | subscription id của SimpMessageHeaderAccessor |
| id trong SUBSCRIBE/UNSUBSCRIBE | subscription id theo ngữ cảnh command |
| x-trace-id | Native header tùy biến, đọc bằng getFirstNativeHeader() |
| receipt | Native STOMP header, đọc qua API StompHeaderAccessor |

StompHeaderAccessor chuyển một số header STOMP chuẩn sang processing header tương ứng để tầng xử lý Spring có API thống nhất. Header giao thức gốc vẫn được quản lý trong native header map để có thể tái tạo frame hoặc phục vụ nhu cầu giao thức.

Ví dụ, gọi setDestination("/app/orders") trên StompHeaderAccessor cập nhật destination của Spring và native header destination. Nếu chỉ đặt một generic header tên destination bằng setHeader(), không nên kỳ vọng nó có cùng tác dụng với API chuyên biệt setDestination().

Khi chuyển đổi hai chiều, hãy dùng accessor theo giao thức để mapping nhất quán. Tự sửa trực tiếp một trong hai biểu diễn có thể làm chúng không còn đồng bộ.

## 11. Native header trong custom protocol

Nếu tích hợp một giao thức nội bộ hoặc broker riêng, có thể tạo lớp con của NativeMessageHeaderAccessor. Lớp con nên chịu trách nhiệm:

- Tạo accessor từ header đã parse của giao thức.
- Chuẩn hóa các header chung cần cho Spring processing.
- Giữ các header đặc thù trong native header map.
- Cung cấp getter/setter có kiểu cho những header quan trọng.
- Chuyển Spring Message thành frame hoặc request của giao thức khi gửi ra.
- Xác định rõ quy tắc cho header lặp, giá trị null, encoding và header không được hỗ trợ.

NativeMessageHeaderAccessor có constructor protected nhận map native header hoặc Message. Vì vậy lớp tích hợp có thể gọi super(...) từ constructor của mình. Tuy nhiên, chỉ lưu map là chưa đủ để tích hợp giao thức; cần viết phần chuyển đổi giữa frame bên ngoài và Spring Message ở cả chiều vào lẫn chiều ra.

Không nên tạo một lớp con tổng quát chỉ để chứa các String header nếu dự án đã có accessor chính thức cho giao thức đó. Ưu tiên StompHeaderAccessor hoặc JmsMessageHeaderAccessor để giữ đúng quy tắc mapping mà Spring cung cấp.

## 12. Giới hạn, bảo mật và lỗi thường gặp

### 12.1. Không phải header nào cũng đi xuyên suốt hệ thống

Adapter, message converter, broker hoặc client có thể lọc, đổi tên, chuẩn hóa hoặc loại bỏ header. Việc một giá trị xuất hiện trong native header map của message nội bộ không tự bảo đảm nó sẽ có mặt ở đích cuối. Hãy kiểm tra cấu hình mapping và viết integration test ở ranh giới transport.

### 12.2. Không tin native header như dữ liệu đã xác thực

Native header thường đến từ client hoặc broker bên ngoài. Client có thể tự gửi x-user-id, x-role hoặc x-tenant-id. Không dùng các giá trị này để cấp quyền hoặc xác định danh tính nếu chúng chưa được xác minh bằng cơ chế xác thực phía server.

Dùng Principal đã được Spring Security hoặc tầng xác thực thiết lập cho danh tính người gửi. Nếu cần tenant hoặc correlation id từ header bên ngoài, hãy xác thực định dạng, giới hạn độ dài và kiểm tra quan hệ với session/ngữ cảnh đã xác thực.

### 12.3. Không đưa secret vào header tùy biến

Header có thể được ghi log, hiển thị trong công cụ quản trị hoặc chuyển qua nhiều hệ thống. Không đặt password, access token, API key hay dữ liệu cá nhân nhạy cảm vào native header trừ khi giao thức và kiến trúc bảo mật quy định rõ cách bảo vệ. Khi dùng STOMP qua mạng, bật TLS và quản lý thông tin đăng nhập theo cơ chế xác thực phù hợp.

### 12.4. Không nhầm tên header và API

Các lỗi thường gặp:

- Dùng setHeader() khi muốn gửi header tùy biến ra giao thức.
- Dùng setNativeHeader() cho metadata chỉ phục vụ nội bộ.
- Gọi getFirstNativeHeader() rồi giả định mọi header chỉ có một giá trị.
- Dùng addNativeHeader() mà không kiểm tra giao thức có hỗ trợ header lặp hay không.
- Sửa trực tiếp MessageHeaders thay vì wrap message bằng accessor.
- Sửa map trả về từ toNativeHeaderMap() rồi mong dữ liệu gốc thay đổi.
- Tự đọc destination từ native map trong khi accessor giao thức đã cung cấp getDestination().
- Cho rằng native header của một giao thức sẽ tự động được map sang giao thức khác.
- Tin các header nhận từ client mà không xác thực.

## 13. Kiểm thử native header

Một bộ test nên xác nhận các hành vi sau:

1. Accessor tạo mới ghi đúng native header.
2. setNativeHeader thay thế giá trị cũ.
3. addNativeHeader thêm giá trị theo quy tắc của giao thức.
4. getFirstNativeHeader trả về giá trị đầu tiên và trả null khi không có.
5. removeNativeHeader xóa header tương ứng.
6. toNativeHeaderMap trả bản sao và không cho phép thay đổi map này tác động ngược lên accessor.
7. StompHeaderAccessor đồng bộ destination/content type giữa processing header và native header.
8. wrap(message) giữ được header tùy biến đã được đóng gói trong message.
9. MessageHeaders không bị sửa trực tiếp sau khi message được tạo.
10. Integration test xác nhận header thực sự được gửi/nhận qua transport, nếu ứng dụng phụ thuộc vào việc giữ header qua mạng.

Nên có test cho cả header chuẩn và header tùy biến. Test chỉ đọc lại accessor ngay sau khi set chưa đủ để chứng minh header được serialize, truyền qua broker và được khôi phục đúng ở phía nhận.

## 14. Tổng kết

NativeMessageHeaderAccessor tạo ranh giới rõ giữa metadata nội bộ của Spring và header nguyên bản của giao thức bên ngoài. Native header được lưu trong map nhiều giá trị dưới key NATIVE_HEADERS; accessor cung cấp API để đọc, đặt, thêm và xóa giá trị mà không phải tự thao tác trên cấu trúc nội bộ.

Trong ứng dụng STOMP, hãy ưu tiên StompHeaderAccessor. Dùng các API chung như getDestination() cho thông tin đã được Spring chuẩn hóa, và getFirstNativeHeader()/getNativeHeader() cho header giao thức tùy biến. Khi sửa message hiện có, wrap message thành accessor mutable rồi tạo message mới. Cuối cùng, luôn xác minh mapping ở ranh giới transport và coi native header nhận từ bên ngoài là dữ liệu cần kiểm tra.

## Tài liệu tham khảo

- Spring Framework 6.2.2 — NativeMessageHeaderAccessor: https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html
- Spring Framework 6.2.2 — MessageHeaderAccessor: https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html
- Spring Framework 6.2.x — StompHeaderAccessor: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html
- Spring Framework 6.2.2 — StompHeaders: https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaders.html