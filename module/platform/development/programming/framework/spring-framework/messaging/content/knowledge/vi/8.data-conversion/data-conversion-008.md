# Kiểu đích tổng quát, thông tin phương thức và gợi ý chuyển đổi

## 1. Bài toán: biết payload là gì và consumer cần kiểu nào

Trong Spring Messaging, `Message<T>` cho biết kiểu payload mong đợi ở phía mã Java. Tuy nhiên, khi message đi qua converter hoặc transport, dữ liệu có thể đang ở dạng `String`, `byte[]` hay một representation khác. Converter phải biết kiểu Java đích để chuyển payload thành object mà handler có thể sử dụng.

Với kiểu đơn như `Order`, tham số `Class<Order>` thường đủ. Với kiểu generic như `List<Order>`, `Map<String, List<Order>>` hoặc `Envelope<Payment>`, `Class<?>` chỉ giữ kiểu raw ở runtime. `List.class` không chứa thông tin phần tử là `Order`; do type erasure, converter không thể tự suy ra generic argument chỉ từ `List.class`.

Spring cung cấp các công cụ để giữ thông tin kiểu đích:

- `MethodParameter`: mô tả một tham số của method, bao gồm generic type và annotations.
- `ResolvableType`: biểu diễn kiểu có thể chứa generic arguments và hỗ trợ phân giải type variable.
- `SmartMessageConverter`: mở rộng `MessageConverter` bằng một tham số `conversionHint` để caller truyền metadata bổ sung cho quá trình chuyển đổi.

Ba thành phần này giải quyết ba phần khác nhau: method metadata cho biết handler khai báo nhận gì; `ResolvableType` biểu diễn kiểu đó; conversion hint chuyển thông tin cần thiết tới converter.

## 2. Vì sao Class<?> không đủ cho generic type?

Ví dụ:

~~~java
void handleOrders(List<Order> orders) {
    // xử lý danh sách Order
}
~~~

Khi phản chiếu method, `List.class` chỉ là raw class. Hai kiểu `List<Order>` và `List<Customer>` đều có raw class là `List.class`. Nếu converter chỉ nhận `targetClass=List.class`, nó không biết nên tạo phần tử `Order` hay `Customer`.

Vấn đề tương tự xuất hiện với kiểu lồng nhau:

~~~java
Map<String, List<Order>> ordersByRegion;
Envelope<Payment> paymentEvent;
~~~

Chuyển đổi đúng cần giữ toàn bộ cây generic type, không chỉ tên lớp ngoài cùng. Nếu không có metadata generic, JSON converter có thể tạo `List` chứa `LinkedHashMap` thay vì `List<Order>`. Lỗi có thể chỉ lộ ra sau đó khi code ép kiểu phần tử.

Không nên giải quyết bằng cách đoán kiểu dựa trên tên field hoặc dữ liệu JSON. Kiểu đích phải đến từ hợp đồng của consumer, cấu hình endpoint hoặc metadata đã được kiểm soát.

## 3. MethodParameter: lấy kiểu từ chữ ký phương thức

`org.springframework.core.MethodParameter` mô tả một tham số cụ thể của một method hoặc constructor. Nó giữ thông tin phản chiếu như:

- `Method`/constructor chứa tham số và chỉ số tham số.
- Kiểu khai báo của tham số, kể cả generic signature.
- Annotations đặt trên tham số.
- Thông tin tên tham số nếu metadata biên dịch cho phép truy xuất.

Ví dụ, với method:

~~~java
void handleOrders(List<Order> orders) {
}
~~~

có thể tạo metadata cho tham số đầu tiên:

~~~java
Method method = Handler.class.getDeclaredMethod("handleOrders", List.class);
MethodParameter parameter = new MethodParameter(method, 0);
~~~

Chỉ số `0` là tham số đầu tiên. `MethodParameter` không tự convert payload; nó cung cấp thông tin để một argument resolver hoặc converter biết kiểu handler cần.

Method metadata cũng có thể chứa annotations dùng cho quy tắc chuyển đổi. Ví dụ, một annotation tùy chỉnh có thể mô tả format ngày hoặc quy tắc deserialize. Converter chỉ nên hỗ trợ các annotation có hợp đồng rõ ràng; không nên dùng reflection để suy đoán logic nghiệp vụ.

## 4. ResolvableType: giữ generic arguments

`org.springframework.core.ResolvableType` biểu diễn một kiểu Java cùng thông tin generic có thể phân giải. Có thể tạo từ `MethodParameter`:

~~~java
ResolvableType targetType = ResolvableType.forMethodParameter(parameter);
Class<?> rawType = targetType.resolve();
Class<?> elementType = targetType.getGeneric(0).resolve();
~~~

Với tham số `List<Order>`, `rawType` là `List.class`, còn generic đầu tiên phân giải thành `Order.class`.

Với kiểu lồng nhau, có thể đi sâu theo từng generic argument:

~~~java
ResolvableType type = ResolvableType.forMethodParameter(parameter);
ResolvableType valueType = type.getGeneric(1);
ResolvableType elementType = valueType.getGeneric(0);
~~~

Nếu kiểu khai báo là `Map<String, List<Order>>`, generic thứ nhất là `String`, generic thứ hai là `List<Order>`, và generic đầu tiên của giá trị đó là `Order`.

`ResolvableType` cũng có thể được tạo từ class, field, method return type hoặc type reference. Khi type variable chưa được ràng buộc bởi lớp/kiểu cụ thể, `resolve()` có thể trả `null` hoặc một kiểu quá tổng quát. Khi đó cần truyền context type rõ ràng hoặc khai báo hợp đồng cụ thể.

## 5. MessageConverter và SmartMessageConverter

`MessageConverter` chuyển đổi giữa payload Java và `Message<?>`. Hai thao tác cơ bản là:

- `toMessage(payload, headers)`: tạo message từ object và metadata.
- `fromMessage(message, targetClass)`: chuyển payload của message thành kiểu Java đích.

`SmartMessageConverter` mở rộng hai thao tác này bằng overload nhận thêm `conversionHint`:

~~~java
Message<?> toMessage(Object payload, MessageHeaders headers, Object conversionHint);
Object fromMessage(Message<?> message, Class<?> targetClass, Object conversionHint);
~~~

`conversionHint` là metadata bổ sung do caller truyền vào. Nó có thể là `MethodParameter`, `ResolvableType` hoặc một đối tượng hint do ứng dụng định nghĩa. Converter phải kiểm tra kiểu hint trước khi sử dụng và có fallback rõ ràng nếu hint không được hỗ trợ.

Không phải mọi converter đều dùng hint. Nếu dùng một `MessageConverter` chỉ hỗ trợ `Class<?>`, generic information có thể bị mất. Khi cần generic target type, hãy chọn hoặc triển khai `SmartMessageConverter` và đảm bảo đường gọi thực sự truyền hint tới converter.

### 5.1. Hint không phải header

`conversionHint` là đối số trong lời gọi Java tới converter. Nó không tự xuất hiện trong `MessageHeaders`, không được serialize cùng payload và không tự đi qua broker.

Điều này quan trọng với message liên tiến trình: một `MethodParameter` chứa reflection object của ứng dụng nhận không thể được gửi từ producer sang broker như một phần hợp đồng. Consumer phải tự biết target type từ method/endpoint của nó, cấu hình schema hoặc một registry được kiểm soát.

Đừng đặt đối tượng `MethodParameter` hay `ResolvableType` vào header với kỳ vọng broker sẽ truyền nguyên vẹn metadata Java đó.

## 6. Content type, target type và conversion hint là ba thứ khác nhau

| Thông tin | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Content type | Payload được biểu diễn bằng format nào? | `application/json`, `text/plain`, `application/octet-stream` |
| Target type | Consumer muốn nhận object Java kiểu nào? | `Order.class`, `List.class`, `Map.class` |
| Generic type metadata | Các tham số generic của target type là gì? | `List<Order>`, `Map<String, List<Order>>` |
| Conversion hint | Có metadata nào giúp converter chọn cách diễn giải? | `MethodParameter`, `ResolvableType`, annotation hoặc hint tùy chỉnh |

Ví dụ, `contentType=application/json` chỉ nói payload là JSON. Nó không nói JSON đó phải được chuyển thành `List<Order>` hay `List<Customer>`. Target raw class `List.class` cũng không giữ generic element type. Converter cần thêm hint hoặc một schema/target type đã biết.

Trong Spring Messaging, `MessageHeaders.CONTENT_TYPE` là header chuẩn để mô tả content type. Hãy dùng giá trị phù hợp với representation thật. Gắn `application/json` không tự serialize một Java object thành JSON; serializer/converter phải thực hiện việc đó.

## 7. Luồng chuyển đổi trong một method-based endpoint

Một đường xử lý điển hình có thể được hình dung như sau:

~~~text
Transport / MessageChannel
        |
        v
Message<?> (payload + headers)
        |
        v
Endpoint / argument resolver
        |  đọc chữ ký handler
        |  tạo MethodParameter
        |  tạo ResolvableType
        v
SmartMessageConverter.fromMessage(
    message, rawTargetClass, conversionHint)
        |
        v
Java object đúng target type
        |
        v
Handler method
~~~

Đây là mô hình khái niệm. Cụ thể adapter/endpoint nào tạo `MethodParameter`, truyền hint gì và chọn converter nào phụ thuộc module Spring đang dùng. Không nên giả định mọi `MessageChannel` hoặc mọi handler tự động sử dụng cùng một conversion pipeline.

## 8. ConversionService khác MessageConverter như thế nào?

`ConversionService` của Spring Core tập trung chuyển một giá trị Java từ kiểu nguồn sang kiểu đích, ví dụ `String` thành `Integer`, hoặc một enum thành chuỗi. Nó có thể được dùng bên trong argument resolution hoặc converter.

`MessageConverter` làm việc ở ranh giới message: nó nhận cả `Message<?>`, có thể xem headers/content type và chuyển payload sang kiểu đích hoặc tạo message từ payload.

`SmartMessageConverter` thêm conversion hint để converter có thể sử dụng generic type, method metadata hoặc thông tin chuyển đổi bổ sung.

Không nên đồng nhất ba abstraction này. `ConversionService` không thay thế việc deserialize JSON; `MessageConverter` không tự quyết định channel/handler; `SmartMessageConverter` không tự cung cấp persistence hay delivery guarantee.

## 9. Xây dựng converter có hỗ trợ generic type

Một converter hỗ trợ generic target nên:

1. Xác định payload representation mà nó hỗ trợ, ví dụ JSON dạng `String` hoặc `byte[]`.
2. Kiểm tra content type khi thông tin này có mặt và từ chối format không hỗ trợ.
3. Xác định target type từ conversion hint trước; nếu không có hint thì fallback về `targetClass`.
4. Chuyển toàn bộ generic type sang kiểu mà thư viện serializer hiểu được.
5. Kiểm tra kết quả và báo lỗi conversion rõ ràng khi JSON sai hoặc target type không phù hợp.
6. Không đoán target type từ dữ liệu không đáng tin cậy hoặc từ tên class tùy ý do producer gửi.

Với Jackson, `JavaType` biểu diễn target type mà `ObjectMapper` dùng khi deserialize. Có thể tạo `JavaType` từ `ResolvableType.getType()` thông qua `TypeFactory.constructType(...)`. Cách này giữ được generic signature như `List<Order>` thay vì chỉ dùng `List.class`.

### 9.1. Fallback khi không có hint

Nếu converter không nhận được `MethodParameter` hoặc `ResolvableType`, có thể dùng `ResolvableType.forClass(targetClass)`. Fallback này đủ cho target không generic như `Order.class`.

Với raw `List.class`, fallback không thể biết kiểu phần tử. Có thể trả về collection của map/object theo hành vi serializer, hoặc từ chối conversion nếu hợp đồng yêu cầu phần tử có kiểu cụ thể. Không nên âm thầm giả vờ rằng generic type đã được giữ.

## 10. Ví dụ hoàn chỉnh: chuyển JSON thành List<Order> bằng MethodParameter

Ví dụ sử dụng Java 17, Spring Messaging 6.2.8 và Jackson 2.18.3. Converter chỉ minh họa chiều nhận JSON `String` thành Java object; chiều `toMessage` trả `null` để thể hiện rằng converter demo không hỗ trợ serialize outbound.

Tạo Maven project:

~~~text
generic-message-conversion/
  pom.xml
  src/main/java/com/example/messaging/GenericMessageConversionDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>generic-message-conversion</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
        <jackson.version>2.18.3</jackson.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>${jackson.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

`src/main/java/com/example/messaging/GenericMessageConversionDemo.java`:

~~~java
package com.example.messaging;

import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.util.List;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.MethodParameter;
import org.springframework.core.ResolvableType;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MessageConversionException;
import org.springframework.messaging.converter.SmartMessageConverter;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public final class GenericMessageConversionDemo {
    private GenericMessageConversionDemo() {
    }

    public record Order(String id, BigDecimal amount) {
    }

    private static void handleOrders(List<Order> orders) {
        // Method signature is used as target-type metadata in this example.
    }

    private static final class JsonHintMessageConverter implements SmartMessageConverter {
        private final ObjectMapper objectMapper = new ObjectMapper();

        @Override
        public Message<?> toMessage(Object payload, MessageHeaders headers) {
            return null;
        }

        @Override
        public Message<?> toMessage(Object payload, MessageHeaders headers, Object conversionHint) {
            return null;
        }

        @Override
        public Object fromMessage(Message<?> message, Class<?> targetClass) {
            return fromMessage(message, targetClass, null);
        }

        @Override
        public Object fromMessage(Message<?> message, Class<?> targetClass, Object conversionHint) {
            if (!(message.getPayload() instanceof String json)) {
                return null;
            }

            ResolvableType targetType;
            if (conversionHint instanceof MethodParameter methodParameter) {
                targetType = ResolvableType.forMethodParameter(methodParameter);
            } else if (conversionHint instanceof ResolvableType resolvableType) {
                targetType = resolvableType;
            } else {
                targetType = ResolvableType.forClass(targetClass);
            }

            JavaType javaType = objectMapper.getTypeFactory().constructType(targetType.getType());
            try {
                return objectMapper.readValue(json, javaType);
            } catch (JsonProcessingException ex) {
                throw new MessageConversionException("Invalid JSON message payload", ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String json = "[{\"id\":\"O-1\",\"amount\":19.95},"
                + "{\"id\":\"O-2\",\"amount\":42.50}]";

        Message<String> message = MessageBuilder
                .withPayload(json)
                .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
                .build();

        Method method = GenericMessageConversionDemo.class
                .getDeclaredMethod("handleOrders", List.class);
        MethodParameter hint = new MethodParameter(method, 0);

        JsonHintMessageConverter converter = new JsonHintMessageConverter();
        Object converted = converter.fromMessage(message, List.class, hint);
        List<?> orders = (List<?>) converted;
        Order first = (Order) orders.get(0);

        ResolvableType targetType = ResolvableType.forMethodParameter(hint);
        System.out.println("targetRawType=" + targetType.resolve().getSimpleName());
        System.out.println("targetElementType=" + targetType.getGeneric(0).resolve().getSimpleName());
        System.out.println("orderCount=" + orders.size());
        System.out.println("firstOrderId=" + first.id());
        System.out.println("firstAmount=" + first.amount().toPlainString());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.GenericMessageConversionDemo
~~~

Stdout:

~~~text
targetRawType=List
targetElementType=Order
orderCount=2
firstOrderId=O-1
firstAmount=19.95
~~~

Điểm cần quan sát:

- `MessageHeaders.CONTENT_TYPE` mô tả payload đang là JSON.
- `List.class` chỉ cung cấp raw target class.
- `MethodParameter` lấy chữ ký `handleOrders(List<Order>)` từ reflection.
- `ResolvableType.forMethodParameter(...)` giữ được generic argument `Order`.
- `SmartMessageConverter` nhận `MethodParameter` qua `conversionHint` và tạo Jackson `JavaType` đầy đủ.
- Kết quả là danh sách có phần tử `Order`, không phải danh sách map không định kiểu.

Converter demo cố ý không hỗ trợ chiều serialize outbound và trả `null` cho `toMessage`. Trong ứng dụng thực tế, hãy triển khai chiều đó hoặc dùng converter khác phù hợp; không coi đoạn code này là converter JSON hai chiều hoàn chỉnh.

## 11. Xử lý lỗi và trường hợp không thể phân giải target type

Chuyển đổi có thể thất bại ở nhiều lớp:

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Payload không đúng representation | Converter mong JSON `String` nhưng nhận `byte[]` hoặc object khác | Thêm hỗ trợ representation đó hoặc trả về không hỗ trợ một cách rõ ràng |
| JSON sai cú pháp | Payload bị hỏng hoặc producer vi phạm hợp đồng | Báo lỗi conversion, cách ly/DLQ theo chính sách message |
| Thiếu generic hint | Chỉ có `List.class`, không biết element type | Cung cấp `MethodParameter`, `ResolvableType` hoặc schema target rõ ràng |
| Type variable chưa được ràng buộc | Generic method/class không có context cụ thể | Resolve bằng containing type hoặc yêu cầu target type tường minh |
| Content type không hỗ trợ | Header mô tả XML/binary nhưng converter chỉ đọc JSON | Chọn converter phù hợp hoặc từ chối message |
| Kiểu field không tương thích | JSON có giá trị sai kiểu/format | Kiểm tra schema, converter config và dữ liệu producer |
| Hint không được converter hiểu | Caller truyền một loại object khác | Bỏ qua theo fallback đã định nghĩa hoặc báo lỗi cấu hình rõ ràng |

Không nên trả `null` cho mọi lỗi. `null` trong hợp đồng converter thường có nghĩa converter không hỗ trợ chuyển đổi message/target đó; lỗi dữ liệu hoặc JSON sai nên được báo bằng exception phù hợp để endpoint có thể áp dụng error handling.

## 12. Generic type metadata và ranh giới transport

`MethodParameter` và `ResolvableType` thường là metadata phía consumer. Khi message qua broker, producer không thể giả định consumer có cùng classpath hoặc cùng method signature.

Đối với tích hợp liên dịch vụ:

- Định nghĩa schema/wire format độc lập với class Java nội bộ.
- Consumer chọn target type dựa trên endpoint hoặc registry được kiểm soát.
- Dùng content type để mô tả format, schema version để mô tả phiên bản hợp đồng.
- Nếu có type header do framework/broker adapter sử dụng, giới hạn các package/type được phép deserialize; không cho payload không tin cậy tự chọn bất kỳ class nào.
- Không serialize `Method`, `MethodParameter`, `ResolvableType` hoặc Java `Class` object như một phần của message contract.

Generic type hint giúp converter ở một process giữ đúng kiểu đích; nó không thay thế schema registry, versioning hoặc validation ở ranh giới dịch vụ.

## 13. Các lỗi thường gặp

- **Chỉ truyền `List.class`:** generic element type bị mất và phần tử có thể thành map.
- **Nhầm content type với target type:** `application/json` không nói JSON phải thành `List<Order>`.
- **Cho rằng `Message<T>` giữ generic qua broker:** generic Java không tự tồn tại trong wire format.
- **Không truyền conversion hint:** converter chỉ thấy raw class và không thể tạo đúng generic type.
- **Giả định mọi MessageConverter đều dùng hint:** chỉ `SmartMessageConverter` cung cấp overload hint; caller cũng phải gọi đúng overload.
- **Đưa MethodParameter vào header:** reflection metadata là thông tin nội bộ consumer, không phải transport contract.
- **Đoán target type từ tên class do producer gửi:** có thể tạo lỗ hổng deserialize và phụ thuộc classpath.
- **Không xử lý type variable chưa resolve:** converter có thể âm thầm fallback sang `Object` hoặc kiểu quá tổng quát.
- **Trả null cho payload sai định dạng:** làm lỗi dữ liệu bị hiểu nhầm thành converter không hỗ trợ.
- **Không kiểm tra object sau conversion:** kiểu Java đúng chưa đảm bảo dữ liệu thỏa bất biến nghiệp vụ.

## 14. Checklist thiết kế và review

1. Consumer cần kiểu đơn hay kiểu generic lồng nhau?
2. `targetClass` có đủ biểu diễn kiểu đích không?
3. Nếu target generic, metadata đến từ `MethodParameter`, `ResolvableType` hay schema/configuration nào?
4. Caller có truyền hint vào overload của `SmartMessageConverter` không?
5. Converter có kiểm tra loại hint và fallback rõ ràng không?
6. `ResolvableType` có resolve được generic arguments hay còn type variable chưa ràng buộc?
7. Content type có khớp representation thực tế không?
8. Serializer có chuyển target type thành `JavaType`/type token đầy đủ không?
9. Lỗi JSON, kiểu field, format và schema có được phân loại đúng không?
10. Hint có bị nhầm với header hoặc transport metadata không?
11. Có giới hạn các type được phép deserialize từ message bên ngoài không?
12. Consumer có validate bất biến nghiệp vụ sau conversion không?

## 15. Ghi nhớ

`Class<?>` mô tả raw target type và không giữ generic arguments như `List<Order>`. `MethodParameter` lấy thông tin tham số từ chữ ký method, còn `ResolvableType` biểu diễn và phân giải generic type. `SmartMessageConverter` bổ sung `conversionHint` để caller truyền `MethodParameter`, `ResolvableType` hoặc metadata chuyển đổi khác tới converter. Content type mô tả format của payload; target type mô tả object Java consumer cần; conversion hint bổ sung thông tin để converter thực hiện việc chuyển đổi chính xác. Hint là metadata trong lời gọi nội bộ, không tự đi qua broker. Với message liên dịch vụ, hãy dùng schema/versioning và target type được consumer kiểm soát; không dựa vào reflection object hoặc tên class tùy ý từ producer.