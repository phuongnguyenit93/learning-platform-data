# StreamMessage và chuỗi giá trị có kiểu trong JMS / Spring JMS

## 1. StreamMessage là gì?

`StreamMessage` là một trong năm kiểu **body** của JMS (Java Message Service, ngày nay là đặc tả **Jakarta Messaging**). Nó lưu một **chuỗi có thứ tự** gồm những giá trị Java primitive, `String` và `byte[]` được provider hỗ trợ. Producer ghi từng giá trị nối tiếp bằng các phương thức như `writeString()`, `writeInt()`, `writeDouble()`; consumer đọc **theo đúng thứ tự tương ứng** bằng `readString()`, `readInt()`, `readDouble()`.

Ví dụ message có cấu trúc logic:

~~~text
Body của StreamMessage:
  [0] String  = "ORDER"
  [1] int     = 42
  [2] double  = 18.75
  [3] boolean = true
  [4] byte[]  = [1, 2, 3]

Đọc hợp lệ theo schema:
  readString()  → "ORDER"
  readInt()     → 42
  readDouble()  → 18.75
  readBoolean() → true
  readObject()  → byte[] {1, 2, 3}
~~~

**Điểm cốt lõi:** `StreamMessage` là **dãy các trường có kiểu, có vị trí**; nó **không phải** `java.util.stream.Stream`, không phải luồng dữ liệu TCP liên tục, và cũng không phải đối tượng tùy ý được serialize vào message. Khi gửi một message, ứng dụng đã ghi body theo các trường của schema. Khi nhận, consumer phải hiểu schema đó và đọc tuần tự.

Trong bối cảnh Spring Framework, `JmsTemplate` có thể gửi/nhận chính `StreamMessage`, nhưng cần chủ động xây dựng và phân tích body của message. `JmsTemplate` không tự suy ra schema vị trí của các giá trị.

### 1.1. Vị trí trong mô hình JMS Message

~~~text
JMS Message
├─ Headers    (JMSMessageID, JMSCorrelationID, JMSDestination, ...)
├─ Properties (schemaVersion, producerName, businessType, ...)
└─ Body       (StreamMessage: các trường được ghi liên tiếp)
               ┌─────────┬─────┬───────┬───────┬────────────┐
               │ String  │ int │double │boolean│ byte[]     │
               ├─────────┼─────┼───────┼───────┼────────────┤
               │ "ORDER" │ 42  │ 18.75 │ true  │ {1,2,3}    │
               └─────────┴─────┴───────┴───────┴────────────┘
~~~

`Headers` và `Properties` có API riêng. Giá trị trong `StreamMessage` **không tự có tên trường**; nếu cần routing/filtering theo một thuộc tính, đặt nó trong message property, ví dụ `message.setIntProperty("schemaVersion", 1)`. Không nhầm `getIntProperty(...)` với `readInt()`:

- `getIntProperty("schemaVersion")` lấy thuộc tính theo **tên** và không làm thay đổi vị trí đọc body.
- `readInt()` lấy **trường body kế tiếp** và di chuyển con trỏ đọc.

## 2. Khi nào dùng StreamMessage? So sánh với các message type khác

| Kiểu JMS message | Body đại diện cho | Cách truy cập | Phù hợp |
| --- | --- | --- | --- |
| `TextMessage` | Một `String` | `getText()` | JSON, XML, plain text |
| `BytesMessage` | Dãy byte nhị phân | Đọc byte/primitive bằng các hàm `read...`, tự quản lý định dạng nhị phân | Binary protocol đã xác định, byte-level layout |
| `MapMessage` | Các cặp **tên → giá trị** có kiểu | `getInt("quantity")`, `getString("type")` | Bộ trường có tên, truy cập không cần thứ tự |
| `StreamMessage` | **Chuỗi giá trị có kiểu theo vị trí** | `readString()`, `readInt()`, `readObject()` theo thứ tự | Format tuần tự đơn giản, consumer biết chính xác thứ tự/kiểu |
| `ObjectMessage` | Đối tượng Java `Serializable` | `getObject()` | Tích hợp Java dùng serialization theo hợp đồng chặt chẽ; cần đánh giá an toàn và tương thích |

Ví dụ hai thông điệp có dữ liệu giống nhau nhưng cách hiểu khác nhau:

~~~java
// Mảnh code minh họa trong callback có jakarta.jms.Session session:
StreamMessage stream = session.createStreamMessage();
stream.writeString("BOOK"); // phần tử vị trí 0
stream.writeInt(3);         // phần tử vị trí 1

MapMessage map = session.createMapMessage();
map.setString("kind", "BOOK");
map.setInt("quantity", 3);  // đọc bằng tên, không phụ thuộc vị trí
~~~

Với `StreamMessage`, consumer phải **biết** vị trí 0 là loại hàng, vị trí 1 là số lượng. Với `MapMessage`, consumer tra theo tên `kind`, `quantity`. Hai loại message có cùng ý nghĩa nghiệp vụ nhưng không tương đương ở tầng API.

**Không dùng StreamMessage chỉ vì muốn “streaming” file lớn.** Đây là format body tuần tự của một JMS message; ứng dụng/broker vẫn chịu giới hạn kích thước message và bộ nhớ. Truyền file hoặc dữ liệu lớn cần chiến lược chunking, object storage hoặc giao thức chuyên dụng theo yêu cầu tải thực tế.

## 3. API tạo và ghi chuỗi giá trị

Với **Jakarta Messaging** (`jakarta.jms.*`, dùng trong Spring Framework 6+/Spring Boot 3+), cách tạo message là:

~~~java
StreamMessage message = session.createStreamMessage();
message.writeString("ORDER");
message.writeInt(42);
message.writeDouble(18.75);
message.writeBoolean(true);
message.writeBytes(new byte[] {1, 2, 3});
~~~

`session` ở đây là một `jakarta.jms.Session` do JMS provider cấp; ví dụ **chỉ là mảnh code** và cần đặt trong phương thức có quyền ném `JMSException`. Với API JMS đời cũ dùng `javax.jms.*`, hãy dùng đúng một thế hệ thư viện trong cùng project.

### 3.1. Phương thức write/read tương ứng

| Kiểu giá trị | Ghi vào StreamMessage | Đọc trực tiếp |
| --- | --- | --- |
| `boolean` | `writeBoolean(boolean)` | `readBoolean()` |
| `byte` | `writeByte(byte)` | `readByte()` |
| `short` | `writeShort(short)` | `readShort()` |
| `char` | `writeChar(char)` | `readChar()` |
| `int` | `writeInt(int)` | `readInt()` |
| `long` | `writeLong(long)` | `readLong()` |
| `float` | `writeFloat(float)` | `readFloat()` |
| `double` | `writeDouble(double)` | `readDouble()` |
| `String` | `writeString(String)` | `readString()` |
| `byte[]` | `writeBytes(byte[])` hoặc `writeBytes(byte[], off, len)` | `readBytes(byte[])` hoặc `readObject()` |
| Wrapper primitive, `String`, `byte[]` | `writeObject(Object)` | `readObject()` |

`writeObject(...)` **không có nghĩa** ghi được một Java object tùy ý. API chỉ cho phép wrapper của primitive (như `Integer`, `Boolean`, `Double`), `String` và `byte[]`. Ví dụ:

~~~java
message.writeObject(Integer.valueOf(7));     // hợp lệ: tương đương writeInt(7)
message.writeObject("hello");                // hợp lệ: tương đương writeString
message.writeObject(new byte[] {10, 20});    // hợp lệ: một trường byte[]

// Không hợp lệ với StreamMessage:
// message.writeObject(new java.util.ArrayList<String>());
// message.writeObject(new java.math.BigDecimal("12.5"));
~~~

Với đối tượng không thuộc loại được hỗ trợ, provider phải báo lỗi định dạng (thường là `MessageFormatException`), **không tự serialize object** giống `ObjectMessage`. Nếu dữ liệu nghiệp vụ là một object gồm nhiều field, cần thống nhất cách map object thành trường của `StreamMessage` hoặc dùng một format khác, ví dụ JSON trong `TextMessage`.

### 3.2. Một lần ghi tạo ra một trường theo vị trí

~~~java
message.writeInt(10);     // field #0: int 10
message.writeString("A"); // field #1: String "A"
message.writeInt(20);     // field #2: int 20
~~~

Consumer đọc:

~~~java
int first = message.readInt();      // 10
String second = message.readString(); // "A"
int third = message.readInt();      // 20
~~~

Ở ví dụ đọc, `message` phải **đang ở read-only mode và con trỏ tại đầu**. Đối với message producer vừa tạo, gọi `reset()` trước khi tự đọc thử; đối với message vừa receive, provider đã chuẩn bị read-only mode. Đây là khác biệt quan trọng so với các API thông thường chỉ dùng getter/setter.

Không có hàm chuẩn kiểu `getField(2)` hay `get("quantity")` cho `StreamMessage`. Muốn truy cập field thứ ba, đọc/tiêu thụ các field trước nó theo hợp đồng; nếu cần đọc lại, `reset()` đưa con trỏ về đầu nhưng không cho nhảy ngẫu nhiên tới vị trí bất kỳ.

## 4. Vòng đời body: write-only, reset, read-only và clearBody

### 4.1. Sơ đồ trạng thái

~~~text
session.createStreamMessage()
          │
          ▼
      WRITE-ONLY
  (writeInt / writeString /...)
          │
          │ reset() hoặc message đã được gửi/nhận
          ▼
      READ-ONLY
  (readInt / readString /...)
          │                  │
          │ reset()          │ clearBody()
          ▼                  ▼
      READ-ONLY          WRITE-ONLY (body rỗng)
  (con trỏ về đầu)      (ghi lại body mới)
~~~

- **Khi mới tạo:** body **write-only**; có thể `write...()`, nhưng gọi `read...()` sẽ phát sinh `MessageNotReadableException`.
- **`reset()`:** đặt body ở **read-only mode** và đưa con trỏ về đầu; không xóa dữ liệu. Gọi lại `reset()` khi đã đọc có thể đọc từ đầu.
- **Khi message được receive:** provider đã chuẩn bị body ở read-only mode; consumer có thể `read...()` trực tiếp. Không nhất thiết gọi `reset()` trước lần đọc đầu.
- **Khi đang read-only:** gọi `write...()` gây `MessageNotWriteableException`.
- **`clearBody()`:** xóa **body** và đưa về write-only mode để xây dựng body mới. Nó **không xóa headers/properties**; muốn xóa properties dùng `clearProperties()`.
- **Gửi message:** provider chịu trách nhiệm đưa bản message gửi đi theo API. Không coi việc giữ lại object local sau `send` là một stream còn mở xuyên mạng; một message đã gửi có thể được client tiếp tục thao tác mà không sửa bản đã gửi.

### 4.2. Ví dụ reset và clearBody

Đoạn sau là **mảnh code chạy trong một callback có `Session session`**, dùng để quan sát state:

~~~java
StreamMessage m = session.createStreamMessage();
m.writeInt(7);
m.writeString("ok");

// m.readInt();   // sai: MessageNotReadableException (write-only)

m.reset(); // chuyển sang read-only và về đầu
System.out.println(m.readInt());
System.out.println(m.readString());

m.reset(); // về đầu, không xóa body
System.out.println(m.readInt());

// m.writeInt(8); // sai: MessageNotWriteableException (read-only)

m.clearBody(); // xóa body; write-only trở lại
m.writeString("changed");
m.reset();
System.out.println(m.readString());
~~~

Stdout (khi provider bình thường):

~~~text
7
ok
7
changed
~~~

**Không gọi `clearBody()` chỉ để đọc từ đầu:** lệnh này xóa dữ liệu. Dùng `reset()` để đọc lại; dùng `clearBody()` khi chủ động xây dựng một body mới.

## 5. Quy tắc đọc tuần tự và phép chuyển kiểu được JMS cho phép

### 5.1. Thứ tự quan trọng hơn tên biến

Giả sử producer ghi:

~~~java
message.writeInt(42);
message.writeString("ORDER");
message.writeBoolean(true);
~~~

Consumer phải đọc field #0 trước field #1:

~~~java
int id = message.readInt();           // field 0: 42
String kind = message.readString();   // field 1: "ORDER"
boolean active = message.readBoolean(); // field 2: true
~~~

Nếu consumer gọi `readBoolean()` ngay tại field `int`, kiểu chuyển đổi không hợp lệ và sẽ gặp `MessageFormatException`. Vì message **không tự ghi tên các field vào body**, không thể gọi `readString()` để “nhảy” đến trường kind: lời gọi đầu tiên sẽ áp dụng lên **field 0**. Một vài phép chuyển kiểu hợp lệ có thể che giấu sai schema: ví dụ `readString()` được phép đọc field `int` và trả chuỗi, nhưng việc đó vẫn tiêu thụ **field 0** chứ không chuyển sang field `String` mà người gọi mong đợi.

### 5.2. Bảng chuyển kiểu được cho phép

Đặc tả JMS đưa ra bảng conversion cho `StreamMessage`. Bảng dưới tóm tắt **kiểu ghi** ở cột trái và **các hàm đọc có thể dùng** ở cột phải (ngoài `readObject()`):

| Field đã ghi | Các kiểu được phép khi đọc |
| --- | --- |
| `boolean` | `boolean`, `String` |
| `byte` | `byte`, `short`, `int`, `long`, `String` |
| `short` | `short`, `int`, `long`, `String` |
| `char` | `char`, `String` |
| `int` | `int`, `long`, `String` |
| `long` | `long`, `String` |
| `float` | `float`, `double`, `String` |
| `double` | `double`, `String` |
| `String` | `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `String` |
| `byte[]` | `byte[]` thông qua `readBytes(byte[])`; `readObject()` cũng nhận được một `byte[]` |

Ví dụ các chuyển đổi hợp lệ:

~~~java
// Khi đang ở write-only:
message.writeByte((byte) 7);
message.writeInt(42);
message.writeFloat(2.5f);
message.writeString("123");

message.reset(); // giờ mới đọc
int a = message.readInt();       // widening byte -> int: 7
String b = message.readString(); // int -> String: "42"
double c = message.readDouble(); // widening float -> double: 2.5
int d = message.readInt();       // parse String "123" -> int: 123
~~~

Điều cần ghi nhớ:

1. **Không phải mọi chuyển đổi Java tự động đều được JMS hỗ trợ.** Ví dụ `int → double` là widening hợp lệ trong nhiều biểu thức Java, nhưng **không phải conversion được phép của `StreamMessage`**. `message.writeInt(42); message.reset(); message.readDouble();` là lỗi định dạng. Phải đọc `int` rồi tự cast `double` trong code nếu muốn.
2. **Chuỗi thành số cần parse được.** `writeString("abc")` rồi `readInt()` có thể ném `NumberFormatException` (runtime), ngoài lỗi định dạng JMS trong các tình huống khác.
3. **Chuỗi thành boolean cần rõ ràng.** Java `Boolean.valueOf("yes")` cho `false`; vì thế các chuỗi như `"yes"`, `"1"` không nên coi là biểu diễn boolean an toàn. Định nghĩa rõ `"true"` / `"false"` hoặc dùng trực tiếp `writeBoolean()`.
4. **Không có narrowing tùy tiện.** Một field `long` không được đọc bằng `readInt()` chỉ vì giá trị nhỏ; `double` không đọc bằng `readFloat()`.
5. **`readObject()`** lấy field kế tiếp dưới dạng Java wrapper phù hợp: `writeInt(42)` cho `Integer`; `writeBoolean(true)` cho `Boolean`; `writeBytes(...)` cho `byte[]`. Nó không làm thay đổi tập kiểu được phép ghi.

### 5.3. `readObject()` là đọc field, không phải deserialize object bất kỳ

~~~java
message.writeInt(42);
message.writeBoolean(true);
message.writeString("done");
message.reset();

Object x = message.readObject(); // Integer(42)
Object y = message.readObject(); // Boolean.TRUE
Object z = message.readObject(); // "done"
~~~

Đây không phải `ObjectInputStream.readObject()` hoặc `ObjectMessage.getObject()`. Không dùng nó để tự động “đọc nguyên record” thành `OrderDto`. Nếu muốn record, tự map từng field và validate schema trước khi tạo DTO.

## 6. Trường byte[] trong StreamMessage: những bẫy khó nhận ra

`StreamMessage` cho phép **một field có kiểu `byte[]`** nằm giữa các field khác. Không nhầm điều này với toàn bộ `BytesMessage` hoặc cách đọc `readByte()`.

Ví dụ producer:

~~~java
message.writeString("BINARY");
message.writeBytes(new byte[] {10, 20, 30, 40, 50});
message.writeInt(9);
~~~

Consumer có hai cách đọc field byte[]:

### 6.1. Cách đơn giản: `readObject()`

~~~java
message.reset();
String label = message.readString(); // "BINARY"
byte[] bytes = (byte[]) message.readObject();
int version = message.readInt();     // 9
~~~

Khi dùng `readObject()`, field byte[] được trả thành một mảng; đây thường là lựa chọn đơn giản khi kích thước mảng vừa phải. Nếu đang **đọc dở** field byte[] bằng `readBytes(...)`, không chuyển sang `readObject()` để “đọc nốt”.

### 6.2. Cách dùng buffer: `readBytes(byte[])`

API `readBytes(byte[] buffer)` đọc **các byte của một field byte[]** vào buffer đã cấp. Giá trị trả về là số byte đọc trong lần đó, **không phải tổng chiều dài của message**.

~~~java
import java.io.ByteArrayOutputStream;

// Mảnh code trong phương thức, biến message đã reset/readable.
String label = message.readString();
byte[] buffer = new byte[2];
ByteArrayOutputStream out = new ByteArrayOutputStream();

while (true) {
    int count = message.readBytes(buffer);
    if (count > 0) {
        out.write(buffer, 0, count);
    }
    // Nếu đọc được ít hơn kích thước buffer thì đã hết field byte[].
    // -1: null hoặc kết thúc field; 0: field rỗng.
    if (count < buffer.length) {
        break;
    }
}

byte[] bytes = out.toByteArray(); // [10, 20, 30, 40, 50]
int version = message.readInt();  // 9
~~~

Giả sử buffer dài 2 và field có 5 byte, các lần đọc trả **2, 2, 1**. Nếu field có đúng 4 byte, sẽ trả **2, 2, -1**: sau lần đọc đầy buffer cuối cùng cần gọi thêm để xác nhận hết. Nếu field là mảng rỗng, lần gọi đầu trả **0**; nếu field là `null`, trả **-1**. Với mục tiêu phân biệt rõ `null` và mảng rỗng, schema nên quy định cờ hiện diện hoặc dùng `readObject()` cùng kiểu dữ liệu hợp lệ.

**Quy tắc rất dễ sai:** sau lần `readBytes(...)` đầu tiên trên field byte[], **phải đọc hết field đó** trước khi đọc field tiếp theo. Nếu mới đọc 2 trên tổng 5 byte rồi gọi `readInt()`, provider báo `MessageFormatException` vì consumer chưa hoàn tất byte field.

~~~java
// Sai về trạng thái, khi field byte[] dài hơn buffer:
message.readBytes(new byte[2]); // có thể còn byte chưa đọc
int next = message.readInt();    // MessageFormatException
~~~

Một lần `writeBytes(bytes, offset, length)` ghi **một field byte[]** với phần mảng được chọn. Hai lần `writeBytes(...)` nối tiếp tạo **hai field riêng**, không tự ghép thành một field. Consumer phải đọc từng field theo thứ tự.

## 7. Các exception quan trọng

| Exception / tình huống | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `MessageNotReadableException` | Gọi `read...()` khi body còn write-only | Gọi `reset()` trước khi tự đọc message vừa tạo; consumer nhận message thì đã ở read-only |
| `MessageNotWriteableException` | Gọi `write...()` trên body read-only | Nếu muốn thay body, gọi `clearBody()` rồi ghi lại; cân nhắc tạo message mới |
| `MessageFormatException` | Đọc sai kiểu không có trong conversion table; `writeObject` với class không được phép; đọc field mới khi byte[] cũ chưa hoàn tất | Thống nhất schema/phiên bản và kiểu đọc, hoàn tất đọc byte field |
| `MessageEOFException` | Đọc thêm một field khi không còn field trong stream | Dùng schema xác định số/kiểu field; chỉ bắt EOF có chủ đích nếu format cho phép |
| `NumberFormatException` | Cố đọc primitive từ `String` không parse được, ví dụ `"abc"` thành `int` | Validate payload, ưu tiên ghi primitive đúng loại thay vì ép chuỗi |
| `JMSException` khác | Lỗi provider, kết nối, transport, resource | Xem exception/cause, broker log, transaction và retry policy |

**EOF không phải timeout và không phải lỗi broker disconnect.** `MessageEOFException` xảy ra lúc đọc body đã hết field. Timeout nhận message xảy ra ở tầng `receive(timeout)` / `JmsTemplate.receive(...)`, thường khiến lời gọi trả `null`; không được đánh đồng hai hiện tượng.

Ví dụ xác nhận kết thúc stream sau các field đã biết:

~~~java
import jakarta.jms.MessageEOFException;

// Sau khi đã đọc hết các field mà schema mong đợi:
try {
    message.readObject();
    throw new IllegalStateException("Unexpected trailing field");
} catch (MessageEOFException expected) {
    System.out.println("End of stream");
}
~~~

Đây là kiểm tra *không có field dư* khi format yêu cầu độ dài cố định; trong một format cho phép field mở rộng, thay đổi hành vi xử lý tương ứng. Không dùng lỗi EOF để thay hoàn toàn việc version/schema contract.

## 8. Spring JMS: tạo và đọc StreamMessage đúng cách

Spring JMS đặt lớp tiện ích lên API Jakarta Messaging:

- `JmsTemplate.send(destination, MessageCreator)` cho phép tạo **đúng loại JMS message** bằng callback `Session`; với `StreamMessage` nên dùng hình thức này.
- `JmsTemplate.receive(destination)` trả về **raw `jakarta.jms.Message`**, có thể kiểm tra `instanceof StreamMessage` rồi đọc body theo schema.
- `convertAndSend(...)` / `receiveAndConvert(...)` dùng `MessageConverter`; converter mặc định thường xử lý `String → TextMessage`, `byte[] → BytesMessage`, `Map → MapMessage` và Serializable → ObjectMessage`. Nó **không tự biến một record tùy ý thành chuỗi field StreamMessage**.
- Với `@JmsListener`, muốn xử lý `StreamMessage` thì cần đảm bảo listener adapter/converter có thể đưa **raw JMS message** hoặc payload do converter tự viết tới handler; không giả định chỉ khai báo DTO là Spring biết vị trí và kiểu của field.
- `getBody(Class<T>)` của `jakarta.jms.Message` **không được dùng với StreamMessage**: đặc tả yêu cầu lỗi `MessageFormatException`. Hãy dùng `read...()` hoặc `readObject()`.

### 8.1. Demo đầy đủ: Spring Boot 3 và Apache ActiveMQ Artemis

Demo này tạo một StreamMessage có năm field theo schema định nghĩa, gửi vào queue, rồi nhận raw message từ chính queue đó và đọc lại. Yêu cầu: **Java 17+**, **Maven**, **Docker**, broker đang chạy. Phiên bản minh họa **Spring Boot 3.5.7** dùng namespace `jakarta.jms.*`; dự án thực tế nên thống nhất version qua BOM của mình.

**Bước 1. Khởi động Artemis local:**

~~~bash
docker run --rm -d --name stream-jms-broker \
  -p 127.0.0.1:61616:61616 \
  apache/artemis:latest-alpine
~~~

Đây là môi trường học local; image dùng tài khoản lab mặc định `artemis/artemis`. Đợi broker sẵn sàng bằng cách xem log `docker logs stream-jms-broker`. Khi triển khai production, cần cấu hình user/role, TLS, resource limits, queue auto-creation và monitoring riêng.

**Bước 2. Tạo `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-stream-message-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Bước 3. Tạo `src/main/resources/application.properties`:**

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.jms.template.receive-timeout=5s
~~~

Tham số receive timeout ngăn chương trình chờ vô hạn khi không có message; broker demo có thể tự tạo queue theo cấu hình mặc định, nhưng trong production queue nên được khai báo và cấp quyền rõ ràng.

**Bước 4. Tạo `src/main/java/com/example/jms/StreamMessageApplication.java`:**

~~~java
package com.example.jms;

import java.util.Arrays;
import java.util.Locale;

import jakarta.jms.Message;
import jakarta.jms.MessageEOFException;
import jakarta.jms.StreamMessage;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class StreamMessageApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamMessageApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            // Producer ghi 5 field theo schema version 1.
            jmsTemplate.send("demo.stream.orders", session -> {
                StreamMessage message = session.createStreamMessage();
                message.setIntProperty("schemaVersion", 1);
                message.writeString("ORDER");
                message.writeInt(42);
                message.writeDouble(18.75);
                message.writeBoolean(true);
                message.writeBytes(new byte[] {1, 2, 3});
                return message;
            });

            // Receive raw JMS message; không dùng receiveAndConvert().
            Message incoming = jmsTemplate.receive("demo.stream.orders");
            if (incoming == null) {
                System.out.println("Receive timeout");
                return;
            }
            if (!(incoming instanceof StreamMessage stream)) {
                throw new IllegalStateException(
                        "Expected StreamMessage, got "
                                + incoming.getClass().getName());
            }

            // Schema phải giống thứ tự producer đã ghi.
            int schemaVersion = stream.getIntProperty("schemaVersion");
            if (schemaVersion != 1) {
                throw new IllegalStateException(
                        "Unsupported schemaVersion: " + schemaVersion);
            }

            String kind = stream.readString();
            int orderId = stream.readInt();
            double amount = stream.readDouble();
            boolean active = stream.readBoolean();
            byte[] flags = (byte[]) stream.readObject();

            System.out.printf(Locale.ROOT,
                    "version=%d kind=%s id=%d amount=%.2f active=%s bytes=%s%n",
                    schemaVersion, kind, orderId, amount, active,
                    Arrays.toString(flags));

            try {
                // Không còn field nào; minh họa phát hiện EOF.
                stream.readObject();
                throw new IllegalStateException("Unexpected trailing field");
            } catch (MessageEOFException expected) {
                System.out.println("End of stream");
            }
        };
    }
}
~~~

**Bước 5. Chạy ở thư mục chứa `pom.xml`:**

~~~bash
mvn spring-boot:run
~~~

Khi broker hoạt động và message được nhận đúng, hai dòng do code in ra là:

~~~text
version=1 kind=ORDER id=42 amount=18.75 active=true bytes=[1, 2, 3]
End of stream
~~~

Các log khởi động/đóng kết nối của Spring và Artemis có thể xuất hiện thêm. Nếu không nhận được message trong timeout, chương trình in:

~~~text
Receive timeout
~~~

Giải thích theo cơ chế thực thi:

1. `JmsTemplate.send(...)` lấy `Session` từ provider; callback gọi `session.createStreamMessage()` và lần lượt ghi body.
2. `schemaVersion` là **message property** dùng để chọn decoder; nó không phải field #0 và không làm thay đổi vị trí đọc.
3. Provider gửi message qua broker. Consumer dùng `JmsTemplate.receive(...)` để lấy **chính raw JMS Message**.
4. Message đã nhận ở read-only mode; consumer đọc `String, int, double, boolean, byte[]` theo schema. Ở đây dùng `readObject()` cho byte[] vì muốn đọc cả field một lần.
5. `readObject()` sau field cuối ném `MessageEOFException`; code dùng nó để phát hiện số field thừa.
6. Spring quản lý `Session`/`Connection` khi gửi/nhận; việc **tạo và diễn giải field StreamMessage** vẫn do ứng dụng quyết định.

Để dừng broker sau demo:

~~~bash
docker stop stream-jms-broker
~~~

**Giới hạn ví dụ:** nó cố ý gửi rồi nhận trong cùng một ứng dụng cho dễ kiểm tra. Hệ thống thật thường có producer và consumer ở tiến trình độc lập; cả hai vẫn phải đồng ý schema, queue, headers và delivery semantics. Bài demo không chứng minh transaction xuyên database, bảo đảm exactly-once hay recovery sau failover.

### 8.2. Dùng listener bất đồng bộ

Trong hệ thống xử lý message liên tục, consumer thường sử dụng `@JmsListener` hoặc listener container thay vì `receive()` đồng bộ. Với `StreamMessage`, nên xác định chiến lược phân tích payload rõ ràng:

- Nếu handler có thể nhận raw `jakarta.jms.Message`, kiểm tra `instanceof StreamMessage` rồi dùng các phương thức `read...()` theo schema.
- Nếu project dùng converter toàn cục, viết/test custom `MessageConverter` chuyển StreamMessage sang record/DTO dựa trên `schemaVersion` và validate đầy đủ, thay vì phụ thuộc mặc định.
- Khi xử lý lỗi định dạng, quyết định chính sách requeue/retry/DLQ; message bị sai schema có thể lỗi lặp vô hạn nếu cứ redeliver mà không phân loại.

Listener container liên quan acknowledgement và transaction nhưng **không thay thế schema decoder**. Nếu logic đọc body phát sinh exception, việc message có bị gửi lại hay đi DLQ phụ thuộc transaction, acknowledgement, broker redelivery policy và cách framework bắt/xử lý exception.

## 9. Thiết kế schema và tương thích phiên bản

Vì body của StreamMessage không chứa tên field, **schema phải là hợp đồng giữa producer và consumer**. Ví dụ định nghĩa rõ:

| Thứ tự | Kiểu | Tên nghiệp vụ | Quy ước |
| --- | --- | --- | --- |
| Header property | `int` | `schemaVersion` | 1 |
| Field 0 | `String` | `kind` | `"ORDER"` |
| Field 1 | `int` | `orderId` | Số nguyên dương |
| Field 2 | `double` | `amount` | Ví dụ demo; tiền tệ nên dùng minor units/decimal schema tránh làm tròn |
| Field 3 | `boolean` | `active` | Trạng thái kích hoạt |
| Field 4 | `byte[]` | `flags` | Payload nhị phân có mô tả riêng |

### 9.1. Vì sao sửa thứ tự có thể phá consumer?

Producer version 1 ghi `String, int, double`. Producer version 2 tự ý đổi thành `String, double, int`. Consumer version 1 sẽ cố đọc field #1 theo `readInt()` nhưng nhận field `double` và gặp `MessageFormatException`. Ngay cả khi hai phiên bản có conversion hợp lệ, có thể tạo **lỗi dữ liệu âm thầm** do field sai nghĩa.

**Cách quản lý thay đổi:**

1. Có `schemaVersion` trong property hoặc field đầu tiên được thống nhất; consumer đọc version trước khi decode.
2. Viết sơ đồ field **đầy đủ và theo thứ tự**, gồm type, đơn vị, nullability, ràng buộc, byte encoding.
3. Duy trì decoder theo từng phiên bản hoặc dùng chính sách compatibility đã kiểm thử. Với schema nhiều phiên bản, không chèn field bất kỳ vào giữa mà không có version.
4. Với field tùy chọn, quy định rõ flag hiện diện hoặc số lượng field, tránh dựa hoàn toàn vào EOF.
5. Validate dữ liệu sau khi đọc: giới hạn giá trị, độ dài chuỗi và kích thước mảng; đừng tin chỉ vì method đọc được đúng type.
6. Thống nhất cách báo lỗi, retry/DLQ và quan sát schemaVersion để truy vết mismatch.

### 9.2. Khi nào nên dùng format khác?

`StreamMessage` phù hợp khi hai phía do cùng một nhóm kiểm soát, schema ngắn, ít thay đổi và có lợi khi ghi/đọc liên tiếp các primitive có kiểu. Nếu có nhiều ngôn ngữ/framework, field tùy chọn, backward compatibility phức tạp hoặc cần tooling/schema registry, xem xét JSON, Avro, Protobuf... trong `TextMessage` hoặc `BytesMessage`. JMS định nghĩa **API message type**, không tự chuẩn hóa định dạng liên ngôn ngữ và version semantics cho bản ghi nghiệp vụ của bạn.

Nếu dùng `double` cho số tiền, cần lưu ý sai số biểu diễn dấu chấm động. Trường hợp tài chính thường dùng `long` số đơn vị nhỏ nhất (cents, đồng tùy quy ước) hoặc chuỗi decimal có schema, thay vì kỳ vọng `double` chính xác tuyệt đối.

## 10. Các lỗi phổ biến trong code thực tế

### Lỗi 1: Đọc không đúng thứ tự

~~~java
message.writeInt(42);
message.writeString("OK");
message.reset();

// SAI nếu đang mong phần tử đầu là "OK":
String status = message.readString(); // thực tế là "42" do conversion được phép
~~~

Đây là lỗi khó thấy hơn exception: conversion từ `int` sang `String` hợp lệ nên consumer **không báo lỗi**, nhưng business data sai vị trí. Bắt buộc có schema và test thứ tự.

### Lỗi 2: Cho rằng mọi widening của Java đều dùng được

~~~java
message.writeInt(42);
message.reset();
// message.readDouble(); // MessageFormatException: int -> double không được phép
long value = message.readLong(); // 42, hợp lệ: int -> long
~~~

Phải dựa vào bảng conversion của JMS, không dùng trực giác ép kiểu Java.

### Lỗi 3: Quên reset khi đọc message vừa tạo

~~~java
StreamMessage m = session.createStreamMessage();
m.writeInt(1);
// m.readInt(); // MessageNotReadableException
m.reset();
int one = m.readInt(); // 1
~~~

Message **được receive** đã ở read-only; không bắt consumer gọi `reset()` chỉ để đọc lần đầu.

### Lỗi 4: Gọi clearBody chỉ để “rewind”

`clearBody()` **xóa nội dung** và trở lại write-only. Muốn đọc lại từ đầu dùng `reset()`.

### Lỗi 5: Chuyển sang field tiếp theo khi đọc byte[] chưa xong

`readBytes(buffer)` có thể trả bằng chiều dài buffer nhiều lần. Phải tiếp tục đến khi kết quả **nhỏ hơn buffer.length**, kể cả khi cần lần gọi cuối trả `-1`. `readInt()` tiếp theo khi còn byte chưa tiêu thụ gây `MessageFormatException`.

### Lỗi 6: Đọc sai nghĩa của EOF

`MessageEOFException` là hết field trong body; không có nghĩa `receive()` timeout. `readBytes(...)` trả `-1` để báo hết **field byte[]** cũng không phải `MessageEOFException` cho toàn message.

### Lỗi 7: Dùng writeObject với Java entity tùy ý

`StreamMessage.writeObject(new Order(...))` không hợp lệ nếu `Order` không thuộc tập type được JMS cho phép. Muốn chia thành nhiều trường thì tự `writeString/writeInt/...`, hoặc dùng message type/serializer phù hợp.

### Lỗi 8: Dùng convertAndSend để kỳ vọng có StreamMessage

`convertAndSend("demo.stream", orderDto)` đi qua `MessageConverter`. Không có quy tắc mặc định “đưa mỗi property của DTO thành một field StreamMessage”. Dùng `send(..., session -> session.createStreamMessage())` hoặc custom converter đã kiểm thử.

### Lỗi 9: Dùng getBody với StreamMessage

`message.getBody(List.class)`, `message.getBody(byte[].class)` hoặc `getBody(Object.class)` không được dùng để đọc StreamMessage; đặc tả yêu cầu `MessageFormatException` đối với StreamMessage. Đọc bằng API `read...()`.

### Lỗi 10: Không có schemaVersion

Consumer sẽ giải mã sai khi producer thêm, đổi hoặc bỏ field. Thêm version/contract và kiểm tra đầy đủ trước khi xử lý nghiệp vụ.

### Lỗi 11: Bỏ qua transaction, acknowledgement, duplicate

`StreamMessage` chỉ nói về **hình thức body**, không quyết định redelivery, transaction hay thứ tự message giữa các consumer. Với khả năng giao lại sau lỗi, handler phải idempotent khi cần; schema parse failure cần policy DLQ hoặc tránh vòng lặp retry vô tận.

### Lỗi 12: Tin payload từ nguồn không kiểm soát

Consumer không nên ghi database hoặc gọi downstream chỉ dựa vào field đọc được. Validate độ dài `String`, giới hạn số phần tử, size byte[], phạm vi số, unit, quyền gửi và version hợp lệ. Đối với dữ liệu liên ngôn ngữ, thống nhất charset và cách map primitive của provider nếu cần.

## 11. Tự kiểm tra kiến thức

**Câu 1.** `StreamMessage` khác `BytesMessage` như thế nào?  
**Trả lời:** `StreamMessage` là chuỗi **field có kiểu theo vị trí**; `BytesMessage` là luồng byte theo format do ứng dụng tự quản lý. Cả hai đều có thao tác đọc tuần tự nhưng contract body khác nhau.

**Câu 2.** Ghi `writeInt(5)` rồi `reset()`, có đọc bằng `readDouble()` được không?  
**Trả lời:** **Không**; `int → double` không nằm trong bảng conversion được phép. Có thể `readInt()`/`readLong()`/`readString()`.

**Câu 3.** Vì sao `readString()` đôi khi không báo exception dù code đọc sai field?  
**Trả lời:** JMS cho phép chuyển nhiều primitive sang `String`. Consumer vẫn tiêu thụ trường kế tiếp, có thể âm thầm gây lỗi schema.

**Câu 4.** Một field `byte[]` có 4 byte, buffer dài 2. Hai lần `readBytes` trả 2 và 2; đã sẵn sàng đọc field sau chưa?  
**Trả lời:** Chưa. Cần gọi `readBytes` lần nữa để nhận `-1`, xác nhận đã hết field.

**Câu 5.** `reset()` khác `clearBody()` thế nào?  
**Trả lời:** `reset()` đưa con trỏ về đầu và đặt read-only; `clearBody()` xóa body và đặt write-only.

**Câu 6.** Spring `JmsTemplate.convertAndSend(dto)` có mặc định tạo StreamMessage theo thứ tự field của DTO không?  
**Trả lời:** Không. Dùng `send` cùng `MessageCreator` hoặc custom converter chủ động định nghĩa schema.

**Câu 7.** `readObject()` trả về gì sau `writeInt(42)`?  
**Trả lời:** `Integer` biểu diễn 42, không phải một DTO. Sau `writeBytes(...)`, trả `byte[]`.

**Câu 8.** Nếu gọi `readObject()` sau khi đã đọc hết field của StreamMessage?  
**Trả lời:** Ném `MessageEOFException`. Đây là trạng thái đọc body, không phải timeout của `receive()`.

**Câu 9.** Vì sao message property `schemaVersion` tốt hơn chỉ dựa vào EOF?  
**Trả lời:** Consumer biết decoder cần dùng **trước** khi đọc trường body; EOF chỉ cho biết đã hết field, không diễn giải được vị trí/ý nghĩa của các field khác phiên bản.

**Câu 10.** Có nên gọi `getBody(Object.class)` để lấy toàn bộ StreamMessage?  
**Trả lời:** Không. `getBody` không hỗ trợ StreamMessage; dùng các hàm đọc tuần tự.

## 12. Tài liệu chính thức

1. [Jakarta Messaging 3.1 Specification — Message body types, StreamMessage và bảng chuyển kiểu](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
2. [Jakarta EE 11 Javadoc — StreamMessage: mode, read/write, readBytes, readObject, reset](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/streammessage)
3. [Jakarta EE 11 Javadoc — Message: headers, properties, clearBody, getBody](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/message)
4. [Spring Framework Reference — Sending Messages / Message Converters](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html)
5. [Spring Framework Reference — Receiving Messages](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
6. [Spring Framework 6.2.14 Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
7. [Spring Boot Reference — JMS với ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
8. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
