# Chẩn đoán sự cố: Điều kiện SpEL luôn false trong @EventListener

## 1. Dấu hiệu và phạm vi sự cố

Trong Spring Framework, annotation `@EventListener` có thuộc tính `condition` nhận một biểu thức **Spring Expression Language (SpEL)**. Spring chỉ gọi phương thức listener khi biểu thức được đánh giá thành giá trị thỏa điều kiện. Cấu hình rất tiện để lọc event theo trạng thái hoặc dữ liệu, nhưng cũng dễ dẫn đến tình huống “publisher đã gửi sự kiện mà listener hoàn toàn im lặng”.

Ví dụ:

~~~java
@EventListener(condition = "#p0.status() == 'PAID'")
public void handle(PaymentChanged event) {
    System.out.println("Payment paid: " + event.paymentId());
}
~~~

*Đây là đoạn code minh họa trong một Spring-managed bean; `PaymentChanged` là record hoặc class do ứng dụng định nghĩa. Dự án hoàn chỉnh chạy được nằm ở phần 6.*

Nếu phát một `PaymentChanged` có `status = "PENDING"`, việc listener không chạy là **đúng theo thiết kế**. Nhưng nếu event chứa `"PAID"` mà listener vẫn không chạy, phải phân biệt ba trường hợp căn bản:

1. **Condition thực sự cho kết quả false:** listener đã được tìm thấy, event đúng type, expression đã được evaluate, nhưng điều kiện không thỏa.
2. **Không hề đánh giá condition:** event không được gửi đến listener do khác kiểu, bean/annotation chưa đăng ký, sai `ApplicationContext`, sai thời điểm hoặc bị chặn bởi cơ chế transaction.
3. **Lỗi SpEL/đánh giá:** biểu thức sai cú pháp, biến không tồn tại, truy cập thuộc tính sai hoặc method ném exception. Trong luồng đồng bộ mặc định, lỗi này **thường ném exception ra đường gọi publish**; không đồng nghĩa một kết quả false bình thường.

Mục tiêu của quá trình chẩn đoán là xác định chính xác **bước nào đã loại bỏ sự kiện**, không sửa ngẫu nhiên expression hoặc vô hiệu hóa điều kiện trong production.

## 2. @EventListener(condition) hoạt động ra sao?

Cấu hình ví dụ:

~~~java
@EventListener(condition = "#p0.total() >= 1000 and #p0.status() == 'PAID'")
public void onPayment(PaymentChanged event) {
    // Chỉ gọi khi cả hai điều kiện đúng.
}
~~~

Thứ tự xử lý theo quan điểm của người lập trình:

~~~text
Publisher.publishEvent(event)
        |
        v
ApplicationEventMulticaster chọn listener theo event type
        |
        +-- Không khớp type? ---> Không gọi listener, không cần evaluate condition
        |
        v
ApplicationListenerMethodAdapter giải quyết đối số phương thức
        |
        +-- Không có arguments phù hợp? --> Không gọi phương thức
        |
        v
EventExpressionEvaluator đánh giá SpEL condition
        |
        +-- false --> Bỏ qua phương thức listener
        |
        +-- true  --> Gọi phương thức listener
        |
        +-- exception --> Đi vào cơ chế xử lý lỗi, không xem là false
~~~

Với các listener mặc định, không có async executor hay `@Async`, quá trình trên thường được thực hiện trên thread phát sự kiện. Một listener trả về event mới còn có thể kích hoạt những event downstream, nhưng **nếu condition false thì method không chạy và cũng không có event trả về để phát tiếp**.

`condition` nhận **biểu thức SpEL trực tiếp**; không yêu cầu cặp `#{...}` như cú pháp template dùng trong một số ngữ cảnh cấu hình khác. Ví dụ cú pháp đơn giản:

~~~java
@EventListener(condition = "#p0.total() > 1000")
~~~

*Đây là annotation snippet để minh họa; chưa phải chương trình Java độc lập.*

Điều kiện rỗng `condition = ""` nghĩa là listener không áp dụng bộ lọc SpEL này. Spring không tự kiểm tra business status nếu bạn không khai báo.

## 3. Kết quả nào được Spring coi là true?

Theo Javadoc `EventListener.condition`, listener được gọi khi expression có giá trị:

- Boolean `true`.
- Hoặc một chuỗi được Spring chấp nhận để biểu diễn đúng, bao gồm `"true"`, `"on"`, `"yes"` và `"1"`.

Giá trị Boolean `false` không thỏa điều kiện; các biểu thức so sánh dùng trong thực tế nên trả **Boolean rõ ràng** thay vì dựa vào chuyển đổi từ chuỗi.

Ví dụ:

| Expression | Kết quả | Có qua bộ lọc? |
| --- | --- | --- |
| `true` | Boolean `true` | Có |
| `false` | Boolean `false` | Không |
| `1 > 0` | Boolean `true` | Có |
| `'PAID' == 'PENDING'` | Boolean `false` | Không |
| `'yes'` | String `"yes"` | Có theo contract của annotation |
| `'0'` | String `"0"` | Không nên dùng; không phải true token được tài liệu liệt kê |
| `#p0.total() >= 1000` | Phụ thuộc giá trị `total()` | Chỉ khi đúng |

Đừng tự mặc định `null`, chuỗi rỗng hay một đối tượng bất kỳ đều tương đương `false` trong mọi phiên bản hoặc mọi cách đánh giá: một expression trả kiểu bất ngờ có thể gây lỗi chuyển đổi/đánh giá. Khi code là điều kiện lọc, hãy viết các phép so sánh rõ ràng để trả `true` hoặc `false`.

**Quan trọng:** biểu thức đúng cú pháp nhưng mọi event đều có `status = "PENDING"` thì luôn false là điều đương nhiên. Chẩn đoán cần nhìn **dữ liệu thực được publish**, không chỉ nhìn annotation.

## 4. Những biến SpEL Spring cung cấp cho event listener

Spring tạo một **evaluation context dành riêng cho event**. Các đường truy cập đáng nhớ:

| Cách truy cập | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `#p0` | Đối số đầu tiên của phương thức listener | `#p0.status() == 'PAID'` |
| `#a0` | Alias theo chỉ số cho đối số thứ nhất | `#a0.total() >= 1000` |
| `#root.args[0]` | Đối số ở vị trí 0 trong mảng arguments | `#root.args[0].status() == 'PAID'` |
| `args[0]` | Truy cập mảng args qua root object | `args[0].total() > 0` |
| `#payment` | Tham số có tên `payment`, **chỉ khi tên tham số có thể xác định** | `#payment.status() == 'PAID'` |
| `#root.event` | **ApplicationEvent thực tế** được multicaster chuyển đến | Tùy kiểu event và wrapper |
| `event` | Alias của event trên root object | Phải biết event là lớp nào |

Chỉ số bắt đầu ở **0**. Với một method `handle(PaymentChanged event)`, cả `#p0`, `#a0` và `#root.args[0]` đều trỏ tới **tham số listener đã được giải quyết** — trong ví dụ là `PaymentChanged`.

Để tránh phụ thuộc vào compiler metadata, **ưu tiên `#p0` khi listener chỉ có một tham số event**. Muốn expression dễ đọc và dùng tên `#payment`, cần bảo đảm Java compiler có metadata tên parameter phù hợp, thường bằng `-parameters` trong Maven/Gradle, đồng thời kiểm tra tên khai báo chính xác.

### 4.1. Tên tham số không có trong bytecode

Đoạn này chỉ ổn định nếu phương thức thật sự có tên tham số `payment` và tên ấy được Spring nhận ra:

~~~java
@EventListener(condition = "#payment.status() == 'PAID'")
public void handle(PaymentChanged payment) {
    // ...
}
~~~

Nếu đổi tên tham số thành `event` mà không sửa expression, hoặc thiếu metadata tên tham số trong class đã biên dịch, `#payment` có thể không được binding. Tùy expression, điều này có thể dẫn đến **lỗi SpEL**, không nhất thiết là false. Cách giảm rủi ro:

~~~java
@EventListener(condition = "#p0.status() == 'PAID'")
public void handle(PaymentChanged payment) {
    // Không phụ thuộc tên biến payment trong bytecode.
}
~~~

Khi muốn dùng `#payment`, thêm `<parameters>true</parameters>` vào `maven-compiler-plugin` hoặc cấu hình `-parameters` tương ứng; sau đó kiểm thử trên artifact thực sự được triển khai. Không dựa vào việc IDE chạy được còn bản jar CI thì không.

### 4.2. #root.event không giống #p0 đối với payload object

Giả sử publisher phát một record không kế thừa `ApplicationEvent`:

~~~java
context.publishEvent(new PaymentChanged("p-1", "PAID", 1500));
~~~

Spring Framework bao đối tượng đó bằng `PayloadApplicationEvent<PaymentChanged>`. Khi đó:

- `#p0`: thường là chính `PaymentChanged` mà method nhận.
- `#root.event`: là đối tượng `PayloadApplicationEvent` do Spring dùng để multicast.
- `#root.event.payload`: là payload gốc của `PayloadApplicationEvent`.
- `#root.event.source`: là source của wrapper event, **không mặc định là PaymentChanged**.

Vì vậy:

~~~java
// Đúng với listener nhận PaymentChanged làm đối số:
@EventListener(condition = "#p0.status() == 'PAID'")

// Cũng có thể truy cập qua wrapper khi event là payload:
@EventListener(condition = "#root.event.payload.status() == 'PAID'")
~~~

*Đây là các đoạn annotation minh họa đặt trên method listener phù hợp. Với custom class kế thừa `ApplicationEvent`, `#root.event` lại chính là event subclass ấy, không nên gắn cứng quy tắc `payload` cho mọi event.*

Sai lầm thường gặp:

~~~java
// Có thể lỗi property/method vì root.event là wrapper,
// không phải payload business:
@EventListener(condition = "#root.event.status() == 'PAID'")
~~~

Expression này **không được kết luận “luôn false”**: nếu lớp wrapper không có `status()`, Spring có thể ném `SpelEvaluationException` khi đánh giá.

### 4.3. Đừng nhầm #root và #this

Trong SpEL, `#root` chỉ root object của evaluation context, còn `#this` có thể thay đổi ý nghĩa trong các bước chọn/lọc collection. Đối với điều kiện đơn giản trên event payload, `#p0` hoặc `#root.args[0]` thường dễ hiểu và ít nhầm hơn so với cố dựa vào target object ngầm của SpEL.

## 5. Những nguyên nhân khiến SpEL lọc hết mọi event

### 5.1. Sai chữ hoa/chữ thường hoặc khoảng trắng

~~~java
// status thực tế = "paid" hoặc "PAID " -> không khớp:
@EventListener(condition = "#p0.status() == 'PAID'")
~~~

So sánh chuỗi trong ví dụ yêu cầu đúng giá trị. Nếu contract cho phép nhiều cách viết, có thể chuẩn hóa tại producer hoặc thực hiện phép so sánh có chủ đích:

~~~java
@EventListener(condition =
        "#p0.status() != null and #p0.status().trim().equalsIgnoreCase('PAID')")
~~~

*Đây là annotation snippet; không cần chuẩn hóa trên listener nếu schema quy định trạng thái phải đúng định dạng ngay từ producer.*

Với tiền và trạng thái nghiệp vụ có contract chặt, ưu tiên xác thực payload rồi lưu enum/giá trị chuẩn; không để mọi consumer tự chữa một kiểu dữ liệu nhập sai.

### 5.2. Kiểu dữ liệu thực khác điều bạn đang so sánh

Giả sử `status` là Java enum `PaymentStatus.PAID`:

~~~java
public enum PaymentStatus {
    PENDING, PAID, CANCELLED
}
~~~

Viết expression so sánh enum với string dễ gây hiểu nhầm hoặc lệ thuộc conversion. Nên biểu đạt rõ ý định:

~~~java
@EventListener(condition = "#p0.status().name() == 'PAID'")
~~~

*Phương thức của event phải trả enum không null. Nếu cần so sánh trực tiếp với hằng enum trong SpEL, cú pháp `T(com.example.PaymentStatus).PAID` yêu cầu đúng tên lớp/namespace và phù hợp cách nạp class.*

Không tự tin rằng `'PAID'`, `PaymentStatus.PAID` và String từ JSON luôn là cùng kiểu. Kiểm tra **kiểu runtime** và giá trị thật của getter.

### 5.3. Ngưỡng số học và operator biên

~~~java
@EventListener(condition = "#p0.total() > 1000")
~~~

Với `total() == 1000`, điều kiện trên **false**, trong khi `>= 1000` là true. Sai lệch thường xảy ra khi quy tắc nghiệp vụ dùng “từ 1.000 trở lên” nhưng code lại dùng `>`.

| Dữ liệu | `> 1000` | `>= 1000` |
| --- | --- | --- |
| 999 | false | false |
| 1000 | false | true |
| 1001 | true | true |

Cũng nên kiểm tra đơn vị: `totalMinorUnits` (đơn vị nhỏ nhất của currency) khác `totalMajorUnits`. Điều kiện đúng cú pháp vẫn có thể “luôn false” nếu producer gửi 99 thay vì 9.900 do bất nhất đơn vị.

### 5.4. Kiểm tra null, dữ liệu thiếu hoặc field có tên khác

Ví dụ event `PaymentChanged` có `region` tùy chọn. Đừng gọi ngay `#p0.region().equals('VN')` nếu `region()` có thể null. Một cách an toàn:

~~~java
@EventListener(condition =
        "#p0.region() != null and #p0.region().equals('VN')")
~~~

SpEL hỗ trợ toán tử điều kiện và điều hướng an toàn; nếu dùng `?.` hãy vẫn kiểm tra lại kết quả mong muốn khi phần giữa bằng null. **Safe-navigation không biến mọi điều kiện thiếu dữ liệu thành true**.

Sai tên property cũng là lỗi phổ biến. Với JavaBean thông thường `getStatus()`, SpEL có thể truy cập `status`. Với Java record có method `status()`, biểu thức gọi rõ `#p0.status()` giúp tránh ngộ nhận về cú pháp getter và metadata. Trong debug, hãy đối chiếu getter, method thực tế và kiểu event mà listener nhận.

### 5.5. Dùng tham số theo tên nhưng tên không khả dụng

~~~java
@EventListener(condition = "#payment.total() > 1000")
public void onChanged(PaymentChanged event) {}
~~~

Tên `#payment` không trùng với tham số `event`. Vì vậy điều kiện có thể không evaluate được như mong đợi. Đổi sang `#p0.total() > 1000` hoặc sửa tên + compiler metadata, rồi kiểm thử lại. Nếu không có binding hợp lệ, biểu thức có thể **ném exception**, khác với một phép so sánh Boolean false.

### 5.6. Đường truy cập #root.event nhầm payload

~~~java
@EventListener(condition = "#root.event.payload.status() == 'PAID'")
~~~

Cách này hợp lý khi underlying event là `PayloadApplicationEvent`. Nhưng nếu publisher phát một custom `ApplicationEvent` có `getStatus()`, nó **không tự có** property `payload`. Cần chọn expression dựa vào kiểu event thật, hoặc dùng `#p0`/`#root.args[0]` theo tham số listener để giảm ràng buộc với wrapper.

### 5.7. Dữ liệu trong event không phải dữ liệu bạn tưởng

Nếu publisher tạo snapshot với `status=PENDING`, rồi ngay sau `publishEvent(...)` cập nhật database thành PAID, event vừa phát không tự đổi status. Ngược lại, nếu dùng payload mutable và bị thread khác chỉnh trước khi listener chạy, giá trị filter có thể không còn như lúc publish.

**Ưu tiên event payload bất biến**, quan sát status ngay trước lúc phát, và định nghĩa rõ event là snapshot sự thật nào. Trong listener async, đừng suy đoán giá trị event từ trạng thái database ở thời điểm debug nhiều phút sau.

## 6. Ví dụ Java 17+ chạy được: biết khi nào true, false và khi nào không có match

Ví dụ dùng **Spring Framework 6.2.9** với Java 17+ và Maven, không cần Spring Boot, database hay web server. Nó đăng ký bốn listener cho record `PaymentChanged`:

- Một listener **không có condition**, in mọi event đã nhận được để chứng minh event type khớp và listener bean được đăng ký.
- Listener chỉ nhận giao dịch `PAID` có `amount >= 1000`.
- Listener chỉ nhận giao dịch `PAID` nhưng `amount < 1000`.
- Listener lọc `PENDING` qua `#root.event.payload` thay vì `#p0`, minh họa sự khác nhau giữa wrapper và payload.

Các method dùng `@Order` để thứ tự log trong ví dụ **đồng bộ** có thể đối chiếu. Ví dụ chỉ minh họa event filtering, không thực hiện giao dịch tiền tệ thật.

### 6.1. Cấu trúc

~~~text
spel-event-condition-demo/
├── pom.xml
└── src/main/java/EventConditionDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spel-event-condition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/EventConditionDemo.java`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventConditionDemo {

    public record PaymentChanged(
            String paymentId,
            String status,
            int amount) {
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @Order(0)
        @EventListener
        public void onAny(PaymentChanged event) {
            System.out.println("SEEN " + event.paymentId()
                    + " status=" + event.status()
                    + " amount=" + event.amount());
        }

        @Order(10)
        @EventListener(condition =
                "#p0.status() == 'PAID' and #p0.amount() >= 1000")
        public void onLargePaid(PaymentChanged event) {
            System.out.println("MATCH_PAID_LARGE " + event.paymentId());
        }

        @Order(20)
        @EventListener(condition =
                "#a0.status() == 'PAID' and #a0.amount() < 1000")
        public void onSmallPaid(PaymentChanged event) {
            System.out.println("MATCH_PAID_SMALL " + event.paymentId());
        }

        @Order(30)
        @EventListener(condition =
                "#root.event.payload.status() == 'PENDING'")
        public void onPending(PaymentChanged event) {
            System.out.println("MATCH_PENDING " + event.paymentId());
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new PaymentChanged("A", "PAID", 1500));
            context.publishEvent(new PaymentChanged("B", "PAID", 500));
            context.publishEvent(new PaymentChanged("C", "PENDING", 999));
            context.publishEvent(new PaymentChanged("D", "CANCELLED", 2000));
        }
    }
}
~~~

### 6.2. Chạy thử

Trong thư mục có `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventConditionDemo
~~~

**Các dòng do chương trình tự in ra** (không tính thông tin riêng của Maven, nếu có):

~~~text
SEEN A status=PAID amount=1500
MATCH_PAID_LARGE A
SEEN B status=PAID amount=500
MATCH_PAID_SMALL B
SEEN C status=PENDING amount=999
MATCH_PENDING C
SEEN D status=CANCELLED amount=2000
~~~

### 6.3. Vì sao đầu ra này đúng?

1. `AnnotationConfigApplicationContext` quét các bean từ `Config`; bean `Handlers` có bốn method `@EventListener`.
2. `context.publishEvent(new PaymentChanged(...))` công bố một payload object không kế thừa `ApplicationEvent`; hạ tầng Spring bọc nó thành `PayloadApplicationEvent`.
3. `onAny` không có condition nên nhận cả bốn event. `@Order(0)` đặt listener này trước những method có mức ưu tiên lớn hơn trong cấu hình đồng bộ hiện tại.
4. Khi phát `A: PAID/1500`, `#p0.status() == 'PAID'` đúng và `#p0.amount() >= 1000` đúng: in `MATCH_PAID_LARGE A`. Điều kiện `< 1000` không đúng, còn `PENDING` không đúng.
5. Với `B: PAID/500`, listener small-paid in `MATCH_PAID_SMALL B`. Large-paid không chạy vì chưa đạt ngưỡng.
6. Với `C: PENDING/999`, hai điều kiện PAID đều false. `#root.event.payload.status()` đọc trạng thái từ wrapper `PayloadApplicationEvent` và in `MATCH_PENDING C`.
7. Với `D: CANCELLED/2000`, không điều kiện nào thỏa, nên **chỉ** có dòng `SEEN D...`. Đây là minh chứng của filtering đúng chứ không phải listener bị hỏng.

Ví dụ không bật `@Async`, không cấu hình multicaster executor, và không dùng transaction. Vì vậy kết quả được quan sát tuần tự trong một thread. Nếu đổi cấu hình async, **đừng lấy thứ tự stdout của ví dụ làm bảo đảm toàn cục**.

## 7. Quy trình chẩn đoán theo thứ tự, tránh sửa nhầm

### Bước 1: Xác nhận publisher đã phát đúng đối tượng

Ở nơi phát event, ghi log có kiểm soát ngay trước `publishEvent(...)`:

~~~java
logger.info("Publishing PaymentChanged id={} status={} amount={}",
        event.paymentId(), event.status(), event.amount());
publisher.publishEvent(event);
~~~

*Đoạn minh họa cần biến `logger`, `publisher` và `event` trong service tương ứng.*

Xác nhận **kiểu runtime** và **giá trị thực** (không chỉ dựa vào suy đoán từ database hoặc UI). Đừng log payload chứa dữ liệu nhạy cảm. Nếu publisher không chạy hoặc publish đối tượng sai kiểu, sửa source trước khi động tới SpEL.

### Bước 2: Chứng minh event có đến được một listener đúng kiểu

Thêm listener tạm **không có condition**:

~~~java
@EventListener
public void probe(PaymentChanged event) {
    logger.info("Probe received type={} paymentId={}",
            event.getClass().getName(), event.paymentId());
}
~~~

*Đoạn tích hợp đặt trong Spring bean và cần logger phù hợp.*

Nếu probe **không** chạy: vấn đề có thể là bean không được Spring quản lý, event khác kiểu, ngữ cảnh không đúng, listener đăng ký muộn, context đã đóng hoặc lỗi ở nơi publish. Nếu probe chạy mà listener condition không chạy: tập trung kiểm tra expression và dữ liệu.

**Đừng tạm thời thêm probe có side effect vào production**. Nó chỉ nên log các định danh an toàn hoặc dùng trong test.

### Bước 3: Tạm bỏ condition, rồi thay bằng true

Thử trên môi trường kiểm thử:

~~~java
@EventListener
public void onPayment(PaymentChanged event) { /* probe */ }
~~~

Sau đó:

~~~java
@EventListener(condition = "true")
public void onPayment(PaymentChanged event) { /* probe */ }
~~~

Nếu cả hai hoạt động nhưng expression thực tế không hoạt động, lỗi nằm ở **đánh giá condition hoặc dữ liệu được so sánh**, không phải event routing căn bản.

### Bước 4: Chuyển biến theo tên thành #p0

~~~java
// Phụ thuộc tên parameter:
@EventListener(condition = "#payment.status() == 'PAID'")

// Không phụ thuộc tên parameter:
@EventListener(condition = "#p0.status() == 'PAID'")
~~~

*Hai đoạn là annotation snippets; áp dụng một cái tại một thời điểm.*

Nếu cách thứ hai chạy, kiểm tra metadata compiler và tên tham số của method. Với Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

*Snippet Maven này là cấu hình thêm vào `<plugins>` của project đã có plugin compiler; không phải một `pom.xml` đầy đủ. Một số Maven parent/BOM đã bật `-parameters` sẵn, nhưng kiểm thử artifact được deploy vẫn quan trọng.*

### Bước 5: Rút điều kiện thành các mệnh đề độc lập

Nếu condition là:

~~~java
@EventListener(condition =
        "#p0.status() == 'PAID' and #p0.amount() > 1000")
~~~

Hãy kiểm tra riêng từng phần với một event rõ ràng:

~~~text
event.status() = "PAID"
event.amount() = 1000

#p0.status() == 'PAID'  -> true
#p0.amount() > 1000     -> false
Kết hợp bằng 'and'      -> false
~~~

Kiểm tra cả các điểm biên `999`, `1000`, `1001`, và trường hợp `null` hoặc enum. Nếu cả biểu thức dài luôn false, nhiều khi **chỉ một mệnh đề phụ không bao giờ thỏa**.

### Bước 6: Xác nhận kiểu gốc cho #root.event

Nếu method nhận payload record, thử `#p0.status()`. Nếu muốn debug `#root.event`, ghi nhận rằng đó có thể là `PayloadApplicationEvent`. Với custom `ApplicationEvent`, root event là instance của custom subclass. Đừng chọn expression dựa trên tên class method nhận rồi suy ra root event chắc chắn là cùng một đối tượng.

### Bước 7: Tách lỗi SpEL khỏi false

Nếu có stack trace như `SpelEvaluationException` hoặc lỗi gọi method, hãy xử lý như **lỗi expression hoặc dữ liệu**, không phải filter false. Khi listener chạy trên executor hoặc `@Async`, exception có thể được ghi ở thread khác, không quay về caller như lời gọi đồng bộ. Kiểm tra logging và `ErrorHandler`/`AsyncUncaughtExceptionHandler` phù hợp.

### Bước 8: Kiểm tra những gate ngoài SpEL

Nếu vẫn không thấy listener, kiểm tra event type, bean registration, context, lifecycle, transaction phase và điều kiện chạy async. Đặc biệt, `@TransactionalEventListener` mặc định không chạy ngoài transaction phù hợp khi `fallbackExecution=false`, **dù biểu thức condition có thể đúng**.

### Bước 9: Viết regression test cho các giá trị true và false

Đừng chỉ có test “có một event PAID được xử lý”. Hãy xác minh cả event PENDING, amount ở ngưỡng biên, enum/null khi được hỗ trợ và event type không liên quan. Test nên phát event qua một Spring context thật để kiểm tra cả expression context và bean registration.

## 8. Debug SpEL ngoài @EventListener: hữu ích nhưng có giới hạn

Có thể dùng `SpelExpressionParser` trong test để xem một phép so sánh hoạt động ra sao. Ví dụ tạo evaluation context có biến `p0`:

~~~java
var parser = new SpelExpressionParser();
var context = new StandardEvaluationContext();
context.setVariable("p0",
        new PaymentChanged("A", "PAID", 1500));

Boolean match = parser.parseExpression(
        "#p0.status() == 'PAID' and #p0.amount() >= 1000")
        .getValue(context, Boolean.class);

System.out.println(match); // true
~~~

*Đây là đoạn tích hợp minh họa: cần import `org.springframework.expression.spel.standard.SpelExpressionParser`, `org.springframework.expression.spel.support.StandardEvaluationContext` và record `PaymentChanged`. Không phải một file Java độc lập; ví dụ chạy ở phần 6 dùng chính hạ tầng listener để kiểm chứng.*

Điều này kiểm tra **giá trị và cú pháp của biểu thức đã chọn**, nhưng **không tái tạo toàn bộ evaluation context dành riêng cho `@EventListener`**: root object, `#root.event`, biến tên tham số, type resolution và hạ tầng context Spring có thể khác. Vì vậy test quan trọng nhất vẫn là **publish thật trong `ApplicationContext`**.

Nếu biểu thức có gọi bean, property accessor hoặc helper phức tạp, kết quả trong `StandardEvaluationContext` do bạn tự tạo có thể khác với khi Spring xử lý annotation. Không dùng kết quả unit test SpEL thuần để kết luận listener đã được đăng ký đúng.

## 9. Không phải vấn đề nào cũng là SpEL: những trường hợp giống “always false”

| Triệu chứng | Nguyên nhân có thể | Cách phân biệt |
| --- | --- | --- |
| Publisher log đã phát, tất cả `@EventListener` đều không chạy | Sai context, bean không được quản lý hoặc event khác kiểu | Thêm probe không condition, kiểm tra type/context |
| Probe không condition chạy, listener conditional im lặng | Data mismatch, condition false hoặc lỗi SpEL | Tạm thay `condition="true"`, đơn giản hóa expression |
| Có exception ở lúc publish | Lỗi parse/evaluation hoặc listener body (đồng bộ) | Xem stack trace thay vì coi là false |
| Chỉ lỗi khi đóng gói jar, IDE chạy được | Metadata `-parameters` hoặc cấu hình build khác | Đổi sang `#p0`, kiểm tra bytecode/build |
| `@TransactionalEventListener` không chạy ở code không có transaction | Mặc định không fallback ngoài transaction | Test trong transaction đúng hoặc xét `fallbackExecution` |
| Method có `@Async` không thấy log và caller không lỗi | Exception xảy ra ở worker hoặc executor cấu hình sai | Kiểm tra `@EnableAsync`, executor, async error handler |
| Event đã phát trước khi listener bean được đăng ký | Listener không nhận lại event lịch sử | Đăng ký đúng thời điểm hoặc dùng bootstrap listener |
| Method nhận kiểu khác payload thực tế | Spring không route event đến method | Kiểm tra method parameter/event type/generic |
| Dữ liệu trong DB thành PAID nhưng event lọc vẫn false | Snapshot event mang status cũ | Log giá trị ngay tại `publishEvent` |
| Cùng `@EventListener` chạy ở môi trường này nhưng không ở môi trường khác | Bean bị profile/conditional config loại bỏ | Kiểm tra bean registration và cấu hình kích hoạt |

### 9.1. @TransactionalEventListener và fallbackExecution

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#p0.status() == 'PAID'")
public void afterCommit(PaymentChanged event) {
    // Chỉ chạy khi có điều kiện giao dịch và filter phù hợp.
}
~~~

*Snippet tích hợp cần import `@TransactionalEventListener` và `TransactionPhase` cùng bean transaction manager/transaction thích hợp.*

Nếu phát event **không có transaction** mà `fallbackExecution` vẫn để mặc định `false`, listener sẽ không xử lý. Điều này xảy ra **ngay cả khi business status là PAID**; nguyên nhân không nhất thiết là expression trả false.

Nếu bật `fallbackExecution=true`, listener có thể chạy không cần transaction, nhưng làm thay đổi semantics: xử lý không còn bị ràng buộc vào AFTER_COMMIT của giao dịch gốc trong những lần không có giao dịch. Chỉ sử dụng khi đó thực sự là lựa chọn thiết kế.

### 9.2. Không nhầm @ConditionalOnProperty với @EventListener(condition)

Trong Spring Boot, `@ConditionalOnProperty` quyết định **định nghĩa bean/configuration có được đăng ký** dựa trên environment, thường tại startup. `@EventListener(condition=...)` lọc **từng event lúc nhận** bằng SpEL.

Nếu bean chứa listener không hề được tạo do profile/conditional configuration, expression `@EventListener` không có cơ hội được evaluate. Phải xử lý đúng tầng vấn đề.

### 9.3. Event được publish quá sớm

Một `@EventListener` trong bean bình thường không thể lắng nghe những sự kiện Spring Boot xảy ra **trước khi ApplicationContext được tạo và listener methods được đăng ký** (ví dụ `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`). Cần đăng ký listener sớm với `SpringApplication.addListeners(...)` hoặc cơ chế bootstrap khác nếu thật sự cần. Dùng `condition="true"` sẽ không giải quyết được listener đăng ký muộn.

## 10. Các góc cạnh SpEL và thiết kế condition đáng tin cậy

### 10.1. Đừng biến condition thành business engine phức tạp

`@EventListener(condition=...)` phù hợp với bộ lọc ngắn, rõ:

~~~java
@EventListener(condition = "#p0.status() == 'PAID'")
~~~

Nếu cần truy vấn database, gọi API mạng, phân quyền động hoặc kết hợp quá nhiều quy tắc, nên thực hiện trong method listener hoặc một service có test độc lập. SpEL có thể gọi method/bean, nhưng lạm dụng sẽ làm khó debug, tăng chi phí cho mỗi event và che khuất side effect.

Một condition dùng cho bảo mật **không thay thế** kiểm soát quyền ở service/domain layer. Hãy thực thi phân quyền ở nơi thích hợp, không phụ thuộc một annotation filter để chặn mọi đường gọi khác.

### 10.2. Condition không phải công cụ xác thực payload

Nếu `PaymentChanged` quy định `status` bắt buộc có một trong các giá trị `PAID`, `PENDING`, `CANCELLED`, hãy xác thực tại ranh giới tạo event. Đừng dựa vào condition false để âm thầm bỏ mọi event có giá trị status không hợp lệ.

Nên phân biệt:

- **Event không thỏa quy tắc filter**: bỏ qua là hành vi hợp lệ.
- **Event vi phạm contract**: cần metric/log cảnh báo hoặc xử lý lỗi, không mặc định chỉ im lặng.
- **Event cần retry**: phải dùng cơ chế retry/durable delivery riêng khi nghiệp vụ yêu cầu.

### 10.3. Tránh dùng biểu thức nhập động từ nguồn không đáng tin

Annotation `condition` là expression tĩnh trong mã ứng dụng. Không ghép chuỗi input của người dùng rồi tự parse/execute SpEL tùy ý để “linh hoạt điều kiện”: một số khả năng truy cập method/type/bean của SpEL có thể gây rủi ro nghiêm trọng nếu expression do bên ngoài kiểm soát.

Nếu cần lọc theo rule người dùng cấu hình, tạo một DSL/hàm kiểm tra được giới hạn rõ ràng, hoặc cơ chế đánh giá biểu thức được sandbox đúng mục đích — không lấy trực tiếp SpEL đầy đủ làm ngôn ngữ thực thi không kiểm soát.

### 10.4. Enum, null và string contract

Trường `status` trong ví dụ chạy dùng String để minh họa case mismatch. Trong code nghiệp vụ thật, enum hoặc kiểu giá trị có validation thường giúp phát hiện sai dữ liệu sớm hơn.

Cân nhắc null-safety: `#p0.status() != null and #p0.status().equals('PAID')`; toán tử `and` trong SpEL có tính chất short-circuit nên nhánh gọi `equals` không cần chạy khi status null. Nếu event luôn có status không null theo contract, đơn giản hóa filter và bảo vệ invariant ở constructor/validator.

### 10.5. Chi phí đánh giá biểu thức

Biểu thức SpEL được framework xử lý cho event listener phù hợp. Với throughput lớn, tránh filter thực hiện công việc nặng, truy cập IO hoặc cấp phát quá nhiều đối tượng. Nên đo latency/CPU khi có khối lượng event cao và xem xét phân loại event bằng type rõ ràng (ví dụ `PaymentCaptured` thay vì một `PaymentChanged` với hàng chục điều kiện) khi cấu trúc miền nghiệp vụ cho phép.

### 10.6. Logging hữu ích nhưng bảo toàn dữ liệu nhạy cảm

Ở log chẩn đoán, ghi tối thiểu event type, eventId/correlationId (khi có), trạng thái đã chuẩn hóa, ngưỡng và outcome. Tránh dump cả payload chứa thông tin cá nhân/secret. Nếu listener async, log có thể xuất hiện sau log publish và trên thread khác; cần propagation/trace phù hợp nhưng đừng coi thiếu trace ID đồng nghĩa listener không chạy.

## 11. Kế hoạch kiểm thử tối thiểu cho regression

Dùng chính Spring context như phần 6 và kiểm tra các ca:

| Event data | Điều kiện `PAID and amount>=1000` | Kết quả |
| --- | --- | --- |
| `PAID, 1500` | true | LargePaid chạy |
| `PAID, 1000` | true | LargePaid chạy (biên bằng) |
| `PAID, 999` | false | LargePaid không chạy |
| `PENDING, 5000` | false | LargePaid không chạy |
| `CANCELLED, 5000` | false | LargePaid không chạy |
| `paid, 1500` | false nếu không chuẩn hóa case | Không gọi LargePaid |
| `PAID, -1` | false | Điều kiện không đúng; vẫn nên chặn payload sai contract từ producer |

Với method có condition phức tạp, nên có test theo mẫu **positive, negative, boundary, null, wrong-type và invalid expression**. Kiểm tra cả việc listener bean được đăng ký và event thực sự được publish.

Các bước test có thể là:

1. Tạo `AnnotationConfigApplicationContext` thật.
2. Đăng ký bean chứa `@EventListener` và một collector thread-safe khi cần.
3. Publish event có dữ liệu chuẩn xác.
4. Assert listener chỉ được gọi đúng những case mà condition true.
5. Với biểu thức sai property/biến, assert lỗi được phát hiện trong cấu hình sync thay vì kỳ vọng listener lặng lẽ bỏ qua.
6. Nếu có async, dùng `CountDownLatch` hoặc await có timeout, không dùng `Thread.sleep(...)` cố định.
7. Nếu listener giao dịch, kiểm tra đường no-transaction, commit và rollback theo đúng transaction manager của test.
8. Chạy test trên cùng Maven/Gradle compiler settings mà artifact production sử dụng; đặc biệt khi condition tham chiếu tên tham số.

**Không viết test SpEL chỉ bằng cách gọi method handler trực tiếp**: gọi method thường sẽ bỏ qua bộ lọc do Spring quản lý. Phải phát event qua ApplicationContext để kích hoạt condition.

## 12. Checklist xử lý khi production “không có một log nào”

1. **Có thực sự gọi `publishEvent(...)`?** Xác nhận từ log producer có event ID và status ngay lúc phát.
2. **Event type có đúng với tham số listener?** Kiểm tra runtime class, generic và classloader nếu cần.
3. **Listener nằm trong bean đã được Spring quản lý?** Kiểm tra component scan, `@Bean`, profile và đúng context.
4. **Listener có nhận được event khi bỏ condition?** Dùng probe vô tác dụng phụ trong môi trường kiểm thử.
5. **`condition="true"` có hoạt động không?** Nếu có, chuyển sang debug dữ liệu và expression.
6. **Dùng `#p0` thay vì tên tham số có giải quyết vấn đề?** Nếu có, kiểm tra metadata `-parameters`.
7. **Có nhầm `#root.event` với payload không?** Với record được publish trực tiếp, root event có thể là `PayloadApplicationEvent`.
8. **Đã đối chiếu case/null/enum/threshold chưa?** Đặc biệt trường hợp bằng ngưỡng.
9. **Có exception do SpEL nhưng không quan sát đúng log/thread không?** Kiểm tra ErrorHandler và async.
10. **Có gate khác ngoài condition?** `@TransactionalEventListener`, no-transaction, phase, listener đăng ký muộn, context khác.
11. **Có test Spring-context tái hiện được cả true và false?** Chốt lại bằng test bảo vệ lỗi tái diễn.

Sau khi xác định nguyên nhân, ưu tiên sửa **contract dữ liệu, expression rõ ràng hoặc cấu hình runtime**. Không để `condition="true"` trong code production chỉ để “chữa” việc listener im lặng nếu business rule vẫn yêu cầu lọc.

## 13. Bài tập tự kiểm tra

**Câu 1.** Với method nhận `PaymentChanged event` và compiler không giữ parameter names, nên tham chiếu tham số trong SpEL thế nào?

**Đáp án:** Dùng `#p0`, `#a0` hoặc `#root.args[0]`, ví dụ `#p0.status() == 'PAID'`. Những cách này không lệ thuộc vào tên biến Java.

**Câu 2.** Vì sao `#root.event.status()` có thể lỗi khi publisher gọi `publishEvent(new PaymentChanged(...))`?

**Đáp án:** Vì object payload thường được Spring bọc thành `PayloadApplicationEvent`, nên `#root.event` là wrapper chứ không phải `PaymentChanged`. Dùng `#p0.status()` hoặc `#root.event.payload.status()` trong trường hợp phù hợp.

**Câu 3.** Với `status="PAID"` và `amount=1000`, kết quả của `#p0.status() == 'PAID' and #p0.amount() > 1000` là gì?

**Đáp án:** False, do `1000 > 1000` không đúng. Nếu yêu cầu nhận cả giá trị bằng ngưỡng, dùng `>= 1000`.

**Câu 4.** Có thể kết luận “SpEL luôn false” khi listener `@TransactionalEventListener` không chạy ngoài transaction không?

**Đáp án:** Không. Với `fallbackExecution=false` mặc định, listener có thể không được gọi do không có transaction phù hợp, dù condition đúng.

**Câu 5.** Một expression gọi một property không tồn tại của `#root.event`. Spring có luôn trả false âm thầm không?

**Đáp án:** Không. Thường có lỗi đánh giá SpEL (ví dụ `SpelEvaluationException`). Ở listener async, lỗi có thể chỉ thấy trên executor/log/handler riêng.

**Câu 6.** Vì sao chỉ gọi thẳng `handlers.onLargePaid(event)` trong unit test không đủ để kiểm tra condition?

**Đáp án:** Lời gọi Java trực tiếp bỏ qua hạ tầng `@EventListener`; annotation filter được đánh giá khi Spring nhận và phân phối event qua context.

**Câu 7.** Một event có status `paid` (chữ thường), expression `status() == 'PAID'` có match không?

**Đáp án:** Không nếu so sánh chính xác như ví dụ; cần chuẩn hóa status hoặc so sánh không phân biệt case theo contract.

**Câu 8.** Nếu một event duy nhất có cùng status/amount mà listener filter không chạy, bước debug ít xâm lấn nào nên làm đầu tiên?

**Đáp án:** Xác nhận publisher đã phát đúng type/data, sau đó dùng listener không condition hoặc `condition="true"` trong môi trường test để phân biệt routing với expression.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): xử lý event theo type, `@EventListener(condition)` và bảng metadata SpEL (`#root.event`, `#root.args`, `#a0`).
- [Spring Framework 6.2.9 Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html): contract Boolean và các chuỗi true, `condition`, danh sách lớp event, ID listener.
- [Spring Framework 6.2 Javadoc — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/PayloadApplicationEvent.html): wrapper khi công bố object payload.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): toán tử so sánh, logic, xử lý null, property/method access.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, `fallbackExecution` và các phase giao dịch.
- [Spring Framework 6.2 Javadoc — ApplicationListenerMethodAdapter](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ApplicationListenerMethodAdapter.html): xử lý method listener, resolve arguments và kiểm tra điều kiện.
