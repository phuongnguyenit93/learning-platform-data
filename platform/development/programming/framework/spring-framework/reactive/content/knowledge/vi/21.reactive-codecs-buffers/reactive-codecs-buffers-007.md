# retain, release và trách nhiệm khi thao tác bộ đệm trực tiếp trong Spring WebFlux

## 1. Vì sao buffer cần quản lý vòng đời riêng?

Trong Spring WebFlux, dữ liệu HTTP thường đi qua các tầng dưới dạng luồng **Flux<DataBuffer>**. DataBuffer là abstraction của Spring cho byte buffer; tùy server và factory, nó có thể được hỗ trợ bởi heap buffer, direct buffer hoặc bộ đệm được pooling.

Với Reactor Netty, DataBuffer thường bọc một Netty **ByteBuf**. ByteBuf có thể nằm ngoài Java heap và được tái sử dụng từ memory pool. Garbage Collector chỉ quản lý vòng đời object Java; nó không tự giảm reference count của ByteBuf. Vì vậy, code dùng pooled buffer phải tuân thủ quy tắc **retain/release**.

Nếu quên release, buffer có thể không quay lại pool dù object Java không còn được dùng. Nếu release quá sớm hoặc nhiều lần, code khác có thể đọc vùng nhớ đã được giải phóng hoặc nhận IllegalReferenceCountException.

Khi thao tác DataBuffer trực tiếp, phải xác định rõ **ai đang sở hữu buffer, khi nào quyền sở hữu được chuyển giao và ai phải release**.

## 2. DataBuffer, PooledDataBuffer và Netty ByteBuf

### 2.1. DataBuffer là abstraction của Spring

Spring Core cung cấp các kiểu chính:

| Kiểu | Vai trò |
| --- | --- |
| **DataBuffer** | Giao diện đọc/ghi byte, có vị trí đọc/ghi độc lập và có thể pooled |
| **DataBufferFactory** | Tạo hoặc wrap DataBuffer |
| **PooledDataBuffer** | Mở rộng DataBuffer với reference counting |
| **DataBufferUtils** | Tiện ích retain, release, join, đọc/ghi và quản lý buffer |
| **NettyDataBuffer** | DataBuffer bọc Netty ByteBuf |
| **NettyDataBufferFactory** | Tạo DataBuffer dựa trên Netty ByteBufAllocator |

Không phải mọi DataBuffer đều pooled. Ví dụ DefaultDataBufferFactory có thể tạo buffer không dùng reference counting. NettyDataBuffer triển khai PooledDataBuffer và sử dụng reference count của ByteBuf bên dưới.

Vì ứng dụng có thể chạy trên nhiều server/runtime, code Spring nên ưu tiên DataBufferUtils thay vì ép kiểu mọi buffer thành NettyDataBuffer.

### 2.2. PooledDataBuffer

PooledDataBuffer bổ sung các phương thức:

- **retain()**: tăng reference count lên một.
- **release()**: giảm reference count xuống một; khi về 0, buffer được giải phóng hoặc trả lại pool.
- **isAllocated()**: cho biết buffer còn được cấp phát hay đã deallocate.
- **touch(hint)**: gắn thông tin gợi ý phục vụ leak tracking khi implementation hỗ trợ.

Khi một PooledDataBuffer được cấp phát, reference count ban đầu là **1**. Đây là reference đầu tiên mà bên tạo buffer chịu trách nhiệm.

### 2.3. Netty ByteBuf

Netty ByteBuf có các API tương ứng:

- refCnt() đọc reference count hiện tại.
- retain() tăng reference count.
- release() giảm reference count.
- touch(hint) ghi nhận vị trí truy cập để hỗ trợ tìm leak.
- slice() và duplicate() tạo view dùng chung vùng nhớ.
- copy() tạo vùng nhớ độc lập.

Khi reference count về 0, vùng nhớ có thể được trả lại allocator/pool. Nó không nhất thiết được trả ngay cho hệ điều hành.

## 3. Reference counting hoạt động như thế nào?

Giả sử một buffer được tạo với reference count bằng 1:

~~~text
allocate
   |
   v
refCnt = 1
   |
   +-- retain()  ---> refCnt = 2
   |
   +-- release() ---> refCnt = 1
   |
   +-- release() ---> refCnt = 0
                           |
                           v
                    deallocate / pool
~~~

| Thao tác | Reference count | Ý nghĩa |
| --- | ---: | --- |
| Allocate | 1 | Chủ sở hữu ban đầu có một reference |
| retain() | 2 | Có thêm một quyền sử dụng buffer |
| release() | 1 | Một chủ sở hữu hoàn tất |
| release() | 0 | Reference cuối cùng được trả; buffer được deallocate/đưa về pool |

**retain không copy dữ liệu.** Nó chỉ giữ vùng nhớ sống lâu hơn bằng cách tăng reference count.

**release không xóa ngay các byte theo nghĩa Java array.** Nó kết thúc một quyền sở hữu. Khi count về 0, implementation có thể tái sử dụng vùng nhớ; mọi truy cập sau đó đều không hợp lệ.

Nếu truy cập buffer sau khi count về 0, Netty có thể ném **IllegalReferenceCountException**. Gọi release quá số lần retain/allocate cũng có thể làm count âm và gây lỗi tương tự.

### 3.1. Reference count không phải số biến Java đang trỏ tới buffer

Ví dụ:

~~~java
DataBuffer first = buffer;
DataBuffer second = buffer;
~~~

Hai biến trên chỉ là hai alias cùng trỏ đến một object. Chúng **không tự tăng** reference count. Nếu cần hai chủ sở hữu độc lập, phải retain thêm một lần và mỗi chủ sở hữu release đúng một reference.

Tạo thêm biến hoặc truyền cùng object vào method không tự tạo thêm quyền sở hữu.

## 4. Quy tắc ownership: ai phải release?

### 4.1. Chuyển giao ownership

Một component nhận buffer, xử lý xong rồi chuyển buffer cho component tiếp theo. Nếu quyền sở hữu được chuyển giao hoàn toàn, component gửi thường không release nữa; component nhận cuối cùng chịu trách nhiệm.

~~~text
Component A tạo buffer
        |
        v
A chuyển buffer cho B
        |
        v
B đọc / ghi / tiêu thụ xong
        |
        v
B release
~~~

Ví dụ: encoder tạo DataBuffer và phát nó xuống response writer. Encoder đã chuyển buffer cho consumer; writer chịu trách nhiệm release sau khi ghi.

### 4.2. Chia sẻ ownership

Nếu component A vẫn cần dùng buffer trong khi B cũng cần giữ buffer, A phải retain trước khi chia sẻ:

~~~text
allocate: refCnt = 1
        |
        v
retain cho B: refCnt = 2
        |
        +------------------+
        |                  |
        v                  v
A dùng xong, release    B dùng xong, release
        |                  |
        +--------+---------+
                 |
                 v
             refCnt = 0
~~~

Mỗi reference được retain phải có đúng một lần release tương ứng. Không release reference của component khác.

### 4.3. Bảng quyết định

| Tình huống | Trách nhiệm |
| --- | --- |
| Nhận buffer và đọc/tiêu thụ hoàn toàn | Release sau khi xử lý |
| Chuyển buffer nguyên vẹn cho downstream | Chuyển giao ownership; không release ở sender |
| Giữ buffer sau callback hoặc qua tác vụ bất đồng bộ | Retain trước khi giữ; release reference bổ sung khi hoàn tất |
| Tạo buffer mới rồi phát xuống writer | Writer/consumer nhận ownership và release |
| Tạo buffer mới nhưng serialize thất bại trước khi phát | Bên tạo phải release buffer chưa chuyển giao |
| Tạo view chia sẻ vùng nhớ | Kiểm tra reference semantics; retain nếu view phải sống độc lập với owner ban đầu |

Không quyết định ownership chỉ dựa vào tên method. Hãy đọc contract của API đang tạo, nhận hoặc phát DataBuffer.

## 5. Ưu tiên DataBufferUtils thay vì gọi trực tiếp retain/release

Spring cung cấp các tiện ích:

~~~java
DataBufferUtils.retain(buffer);
DataBufferUtils.release(buffer);
DataBufferUtils.touch(buffer, "processing-stage");
~~~

- **DataBufferUtils.retain(buffer)** retain nếu buffer là PooledDataBuffer; nếu implementation không pooled, nó không cần tăng reference count.
- **DataBufferUtils.release(buffer)** giải phóng buffer theo contract của implementation; hỗ trợ PooledDataBuffer và CloseableDataBuffer.
- **DataBufferUtils.touch(buffer, hint)** gắn hint cho buffer pooled hỗ trợ leak tracking.

Các helper này hữu ích khi code làm việc với DataBuffer abstraction mà không biết server đang dùng Netty hay implementation khác.

Giá trị boolean trả về từ release cho biết thao tác có thực sự giải phóng buffer hay không. Với buffer pooled, false thường có nghĩa reference count vẫn còn trên 0; với implementation không pooled, kết quả cũng không có nghĩa là có leak. Đừng dùng boolean đó như bộ đếm ownership tổng quát.

## 6. Tiêu thụ buffer đồng bộ: release trong finally

Nếu code là consumer cuối cùng và chỉ cần đọc byte ngay trong callback, hãy release sau khi đọc. Dùng finally để bảo đảm release cả khi xử lý lỗi:

~~~java
byte[] copyAndRelease(DataBuffer buffer) {
    try {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    } finally {
        DataBufferUtils.release(buffer);
    }
}
~~~

Sau khi copy, byte[] độc lập với buffer gốc. Buffer có thể được release ngay cả khi logic phía sau tiếp tục xử lý byte[].

Nếu chỉ đọc mà quên release, pooled memory có thể bị giữ lại và gây memory leak.

### 6.1. Không release trước khi consumer đọc xong

~~~java
DataBufferUtils.release(buffer);
byte firstByte = buffer.read();
~~~

Đây là use-after-release. Sau khi release cuối cùng, không được đọc, ghi, slice hoặc chuyển buffer sang consumer khác.

### 6.2. Không release hai lần cùng một reference

~~~java
DataBufferUtils.release(buffer);
DataBufferUtils.release(buffer);
~~~

Nếu buffer chỉ có một reference, lần đầu có thể đưa count về 0; lần thứ hai là release dư và có thể ném IllegalReferenceCountException.

Nếu đã retain thêm một reference, hai lần release có thể hợp lệ nhưng phải tương ứng với hai quyền sở hữu khác nhau. Không gọi hai lần chỉ vì code có hai nhánh cleanup mà không có ownership ledger rõ ràng.

## 7. Retain khi cần giữ buffer qua một ranh giới bất đồng bộ

Một callback có thể nhận buffer trong thời gian ngắn nhưng cần tiếp tục dùng dữ liệu sau khi callback kết thúc, chẳng hạn gửi buffer sang tác vụ ghi file bất đồng bộ, chuyển dữ liệu tới hàng đợi khác hoặc giữ tạm để ghép frame.

Nếu nguồn sẽ release reference ban đầu sau khi callback trả về, consumer muốn giữ buffer phải **retain trước khi callback kết thúc**.

Ví dụ về reference bổ sung:

~~~java
DataBuffer retained = DataBufferUtils.retain(buffer);

return writeAsync(retained)
        .doFinally(signal -> DataBufferUtils.release(retained));
~~~

Ý nghĩa:

1. retain tạo một reference riêng cho tác vụ bất đồng bộ.
2. Chủ sở hữu ban đầu vẫn xử lý reference ban đầu theo contract của nguồn.
3. Tác vụ bất đồng bộ release reference đã retain khi complete, error hoặc cancel.
4. writeAsync không được tự release cùng reference thêm lần nữa nếu doFinally đã chịu trách nhiệm.

Đoạn này giả định Publisher được subscribe và tác vụ có thể kết thúc qua complete/error/cancel. Nếu Publisher có thể bị bỏ mà không subscribe, không retain sớm ở assembly time rồi để reference nằm vô chủ. Hãy đặt việc retain trong lifecycle bảo đảm cleanup và xác định rõ ai sở hữu reference ban đầu.

**retain không thay thế cancellation handling.** Nếu task bị hủy, reference được giữ thêm vẫn phải được release. Nếu task đã chuyển buffer sang một component khác, ownership phải được chuyển giao rõ ràng cho component đó.

## 8. Reactor operators có thể loại bỏ buffer: dùng doOnDiscard

Một số operator có thể bỏ phần tử mà downstream không nhìn thấy:

- filter loại phần tử không đạt điều kiện.
- skip bỏ các phần tử đầu.
- take/cancel kết thúc luồng khi vẫn còn phần tử đã được prefetch.
- flatMap, reduce và một số operator có thể prefetch/cache nội bộ.
- Error hoặc cancellation có thể khiến buffer đang chờ bị discard.

Nếu các phần tử bị loại là DataBuffer pooled, chúng vẫn phải được release.

Ví dụ: chỉ giữ buffer có byte đầu tiên là ký tự '{', copy các buffer được giữ và release:

~~~java
Flux<byte[]> jsonChunks = inbound
        .filter(this::startsWithJsonObject)
        .map(this::copyAndRelease)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

- Buffer được filter giữ lại sẽ đi vào copyAndRelease và được release trong finally.
- Buffer bị filter loại sẽ được hook doOnDiscard release.
- Buffer bị discard bởi operator hỗ trợ discard upstream cũng được xử lý nếu hook được đặt đúng trong chain.

**doOnDiscard không thay thế cleanup của buffer được tiêu thụ bình thường.** Nó xử lý phần tử bị operator loại bỏ. Consumer vẫn phải release buffer mà nó nhận và đọc.

Cần đặt doOnDiscard trong composition chain sao cho nó áp dụng được cho operator có khả năng discard. Không thêm một cách máy móc vào mọi Flux; hãy xem operator nào có discard support và ai sở hữu từng buffer.

## 9. Decoder, Encoder và trách nhiệm trong WebFlux

### 9.1. Decoder là consumer cuối của input DataBuffer

Decoder đọc byte từ DataBuffer và chuyển thành object cấp cao hơn. Khi đã đọc xong, decoder phải release input buffer.

Nếu decoder chỉ đọc một buffer rồi release ngay, có thể dùng:

~~~java
DataBufferUtils.release(dataBuffer);
~~~

Nếu decoder dùng operator có thể prefetch, cache hoặc bỏ phần tử như filter/skip, cần thêm doOnDiscard để giải phóng buffer bị loại. Nếu decoder tự giữ buffer qua nhiều bước, nó phải release khi đọc xong và cả khi lỗi/cancel xảy ra trước lúc đọc xong.

### 9.2. Encoder tạo output DataBuffer

Encoder cấp phát DataBuffer để ghi dữ liệu. Nếu serialize lỗi trước khi buffer được phát xuống consumer, encoder phải release buffer:

~~~java
DataBuffer buffer = factory.allocateBuffer();
boolean transferred = false;

try {
    serializeInto(buffer);
    transferred = true;
    return buffer;
} finally {
    if (!transferred) {
        DataBufferUtils.release(buffer);
    }
}
~~~

Đây là mẫu minh họa với serializeInto. Khi buffer được trả về Publisher, ownership đã được chuyển cho consumer tiếp theo. Trong WebFlux, writer ghi response hoặc client request chịu trách nhiệm release các buffer nhận được.

Không release output buffer ngay sau khi emit; writer còn cần đọc nó.

### 9.3. Filter và handler

Với WebFilter hoặc handler thao tác trực tiếp request body:

- Nếu chỉ quan sát metadata rồi chuyển nguyên buffer xuống chain, không release buffer đã chuyển giao.
- Nếu filter đọc và tiêu thụ buffer, filter phải release sau khi đọc.
- Nếu filter giữ buffer để xử lý sau, retain và lập kế hoạch cleanup cho complete/error/cancel.
- Nếu filter bỏ buffer, cần cleanup đúng contract; doOnDiscard phù hợp khi operator discard buffer.
- Nếu filter tạo buffer mới để thay thế buffer cũ, release buffer cũ khi đã tiêu thụ và chuyển buffer mới xuống downstream.

Không tự release một DataBuffer mà framework/consumer tiếp theo vẫn còn quyền sử dụng.

## 10. Thao tác trực tiếp với Netty ByteBuf

### 10.1. Khi nào cần truy cập native buffer?

NettyDataBuffer cung cấp:

~~~java
ByteBuf nativeBuffer = nettyDataBuffer.getNativeBuffer();
~~~

Việc này hữu ích khi tích hợp thư viện Netty cấp thấp hoặc cần API đặc thù của ByteBuf. Tuy nhiên, nó ràng buộc code vào Reactor Netty/Netty implementation. Không ép kiểu một DataBuffer bất kỳ thành NettyDataBuffer nếu chưa biết factory/runtime thực tế.

Trong code Spring thông thường, ưu tiên DataBuffer và DataBufferUtils. Chỉ đi xuống ByteBuf khi cần thiết và đã hiểu ownership của native object.

### 10.2. slice, duplicate và copy

Với Netty ByteBuf:

| API | Vùng nhớ | Reference count |
| --- | --- | --- |
| slice() | Chia sẻ vùng nhớ với buffer gốc | Không tự tăng |
| duplicate() | Chia sẻ vùng nhớ với buffer gốc, có reader/writer index riêng | Không tự tăng |
| retainedSlice() | Chia sẻ vùng nhớ với buffer gốc | Tăng reference count |
| copy() | Tạo vùng nhớ độc lập | Buffer mới có reference count riêng |

Một slice/duplicate không tự tạo một quyền sở hữu mới. Nếu chuyển view đó cho consumer có vòng đời dài hơn buffer gốc, hãy retain trước khi chuyển. Consumer nhận view phải release reference đã được retain.

Ví dụ:

~~~java
ByteBuf view = source.retainedSlice(offset, length);

try {
    inspect(view);
} finally {
    view.release();
}
~~~

Đoạn này phù hợp khi code hiện tại là consumer cuối của view. Nếu chuyển view sang component khác, chuyển luôn trách nhiệm release cho component nhận.

### 10.3. Lưu ý với DataBuffer.slice và retainedSlice

Trong Spring Framework 6, DataBuffer.slice(index, length) và retainedSlice(index, length) đã deprecated để chuyển sang API split(int) có semantics khác. Không sao chép ví dụ slice cũ vào code mới mà không kiểm tra phiên bản và contract.

Khi dùng API mới, đọc Javadoc của đúng phiên bản Spring Framework. Đừng giả định mọi view tạo ra đều tăng reference count hoặc có vòng đời độc lập.

### 10.4. Không release cả wrapper và native buffer cho cùng reference

NettyDataBuffer bọc ByteBuf và cả hai cùng đại diện một vùng nhớ có reference count chung. Nếu gọi nativeBuffer.release() để trả reference cuối, không gọi thêm DataBufferUtils.release(nettyDataBuffer) cho chính reference đó.

Có thể dùng một API nhất quán cho từng reference. Tránh trộn wrapper-level và native-level cleanup mà không theo dõi mỗi lần retain/release.

## 11. Ví dụ Java 17+ chạy được: quan sát retain và release

Ví dụ dùng Spring Boot 3.5.5, Java 17+ và Netty dependency từ spring-boot-starter-webflux. Chương trình tạo một NettyDataBuffer bằng pooled allocator, tăng reference count, rồi mô phỏng hai chủ sở hữu release theo lượt.

Cấu trúc:

~~~text
buffer-ownership-demo/
├── pom.xml
└── src/main/java/example/buffer/BufferOwnershipDemo.java
~~~

### 11.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>buffer-ownership-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.buffer.BufferOwnershipDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.2. BufferOwnershipDemo.java

~~~java
package example.buffer;

import java.nio.charset.StandardCharsets;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.PooledByteBufAllocator;

import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

public class BufferOwnershipDemo {

    public static void main(String[] args) {
        NettyDataBufferFactory factory =
                new NettyDataBufferFactory(PooledByteBufAllocator.DEFAULT);

        NettyDataBuffer buffer = factory.allocateBuffer(16);
        buffer.write("hello".getBytes(StandardCharsets.UTF_8));

        ByteBuf nativeBuffer = buffer.getNativeBuffer();

        System.out.println("initial refCnt = " + nativeBuffer.refCnt());

        // Give a second consumer its own reference.
        DataBufferUtils.touch(buffer, "async consumer");
        DataBufferUtils.retain(buffer);

        System.out.println("after retain = " + nativeBuffer.refCnt());

        // The original owner is finished with its reference.
        boolean senderReleased = DataBufferUtils.release(buffer);

        System.out.println(
                "sender release deallocated = " + senderReleased);
        System.out.println("after sender release = " + nativeBuffer.refCnt());

        // The second consumer releases the retained reference.
        boolean consumerReleased = DataBufferUtils.release(buffer);

        System.out.println(
                "consumer release deallocated = " + consumerReleased);
        System.out.println("after consumer release = " + nativeBuffer.refCnt());
    }
}
~~~

### 11.3. Chạy chương trình

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Stdout:

~~~text
initial refCnt = 1
after retain = 2
sender release deallocated = false
after sender release = 1
consumer release deallocated = true
after consumer release = 0
~~~

Giải thích:

1. Factory cấp phát NettyDataBuffer nên reference count bắt đầu bằng 1.
2. DataBufferUtils.retain tạo thêm một reference, count thành 2.
3. Chủ sở hữu ban đầu release reference của mình; count còn 1 nên chưa deallocate.
4. Consumer thứ hai release reference đã retain; count về 0 và buffer được deallocate/đưa về pool.

Ví dụ kiểm tra trực tiếp reference count của Netty ByteBuf thông qua NettyDataBuffer. Với DataBuffer từ server khác hoặc factory không pooled, không được giả định sẽ có cùng refCnt.

## 12. Ví dụ lỗi và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Quên release buffer sau khi đọc | Pooled memory bị giữ lại, có thể gây leak | Release sau khi consume |
| Release trước khi downstream đọc | Downstream dùng buffer đã deallocate | Chỉ release sau khi consumer cuối hoàn tất |
| Tạo thêm biến rồi nghĩ refCnt tự tăng | Hai alias cùng dùng một reference | Retain khi thật sự chia sẻ ownership |
| Retain nhưng không release | Reference count không về 0 | Gắn cleanup vào complete/error/cancel |
| Release hai lần cùng reference | Reference count có thể về âm | Theo dõi mỗi ownership lease |
| Dùng slice/duplicate rồi chuyển cho async consumer | View có thể chết cùng parent | Retain view trước khi handoff |
| Dùng copy nhưng quên release copy | Buffer mới bị leak | Consumer cuối release copy |
| Filter/skip loại DataBuffer nhưng không cleanup | Buffer bị discard vẫn còn reference | Dùng doOnDiscard đúng vị trí |
| Chỉ xử lý onComplete | Lỗi/cancel bỏ qua cleanup | Xử lý cả complete, error và cancel |
| Release cả ByteBuf và DataBuffer wrapper | Double release cùng reference | Chọn một API cleanup cho mỗi reference |
| Ép mọi DataBuffer thành NettyDataBuffer | Lỗi khi runtime không dùng Netty | Dùng DataBufferUtils và abstraction chung |
| Giữ DataBuffer trong singleton field | Request đồng thời dùng chung buffer/lifecycle | Giữ theo request/task và quản lý ownership riêng |
| Dựa vào GC để giải phóng pooled memory | Ref count không tự giảm khi object unreachable | Release tường minh |

## 13. Tìm memory leak và use-after-release

### 13.1. Dấu hiệu thường gặp

- Netty báo ByteBuf đã bị garbage collect mà release chưa được gọi.
- Native memory hoặc pooled allocator usage tăng dần.
- Dưới tải, lỗi OutOfDirectMemoryError xuất hiện.
- IllegalReferenceCountException khi code đọc/ghi buffer đã deallocate hoặc release quá số lần.
- Lỗi chỉ xuất hiện khi có cancellation, retry, timeout hoặc nhiều request đồng thời.

Một buffer leak không nhất thiết xuất hiện ngay tại request đã tạo nó. Pool có thể tiếp tục giữ vùng nhớ lâu sau khi request kết thúc.

### 13.2. Netty leak detection

Netty cung cấp các mức leak detection:

| Mức | Ý nghĩa |
| --- | --- |
| DISABLED | Tắt phát hiện leak; không nên dùng để che lỗi |
| SIMPLE | Lấy mẫu một phần allocation, chi phí thấp |
| ADVANCED | Thêm access record để truy tìm vị trí sử dụng |
| PARANOID | Theo dõi mọi allocation; hữu ích trong test nhưng có overhead lớn |

Có thể bật advanced leak detection khi điều tra bằng JVM option:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Trong test chuyên biệt có thể dùng PARANOID để bắt lỗi sớm, nhưng không nên giữ mức này trong production vì chi phí theo dõi cao.

### 13.3. Dùng touch để thêm dấu vết

~~~java
DataBufferUtils.touch(buffer, "upload-filter: before forwarding");
~~~

Hint giúp leak detector ghi nhận giai đoạn buffer được truy cập. Nó không tăng reference count, không thay thế retain và không thay thế release.

### 13.4. Kiểm tra cancellation và error path

Đừng chỉ test đường thành công. Kiểm thử:

- Buffer được xử lý hết bình thường.
- Lỗi phát sinh trong lúc đọc/ghi.
- Client hủy request hoặc subscription bị cancel.
- Operator filter/skip loại bỏ buffer.
- FlatMap prefetch rồi upstream error.
- Buffer được chuyển sang async task và task timeout.
- Buffer view được chuyển cho consumer khác.

Mỗi nhánh phải kết thúc với số reference hợp lệ và không để buffer bị giữ lại ngoài dự kiến.

## 14. Quy trình review code khi thao tác DataBuffer trực tiếp

Trước khi merge code xử lý buffer, hãy lần theo từng buffer:

1. **Nguồn tạo:** buffer được allocate, wrap hay nhận từ network?
2. **Reference ban đầu:** ai sở hữu reference đầu tiên?
3. **Handoff:** method nào chuyển quyền sở hữu cho downstream?
4. **Retain:** có thật sự cần chia sẻ hoặc giữ qua callback không?
5. **Release:** mỗi reference được release ở nhánh complete, error và cancel nào?
6. **Discard:** operator nào có thể loại buffer và hook doOnDiscard được đặt ở đâu?
7. **View:** slice/duplicate có chia sẻ vùng nhớ không; reference count có tăng không?
8. **Copy:** buffer copy độc lập nào cần release riêng?
9. **Runtime:** code có phụ thuộc NettyDataBuffer hay dùng được với DataBuffer abstraction?
10. **Kiểm thử:** có test leak/cancel/error và chạy leak detection phù hợp không?

Một review tốt có thể vẽ bảng ownership cho từng buffer: reference ban đầu, các lần retain, chủ sở hữu hiện tại và nơi release. Nếu không thể trả lời ai sẽ release, code chưa hoàn thiện.

## 15. Ghi nhớ

- DataBuffer là abstraction của Spring; chỉ PooledDataBuffer mới có reference counting.
- NettyDataBuffer bọc ByteBuf và chia sẻ reference count với native buffer.
- Reference count ban đầu là 1; retain tăng một; release giảm một; về 0 thì buffer được deallocate/đưa về pool.
- Một biến Java mới không tự tạo reference mới.
- Khi chuyển ownership, bên nhận chịu trách nhiệm release; khi chia sẻ, retain cho owner bổ sung.
- Consumer đọc xong phải release; không release trước khi downstream dùng xong.
- DataBufferUtils.retain/release/touch là lựa chọn phù hợp khi làm việc ở tầng Spring abstraction.
- doOnDiscard xử lý buffer bị operator loại bỏ; nó không thay cleanup của buffer được tiêu thụ bình thường.
- Decoder giải phóng input sau khi decode; response/request writer giải phóng output encoder đã phát.
- Netty slice/duplicate chia sẻ ref count; retainedSlice tăng reference; copy tạo buffer độc lập.
- Xử lý cả complete, error và cancel. Không dựa vào Garbage Collector để release pooled buffer.
- Dùng Netty leak detection và test cancellation để phát hiện lỗi vòng đời.

**Tài liệu chính thức:**
- [Spring Framework — Data Buffers and Codecs: PooledDataBuffer, DataBufferUtils, Decoder và Encoder](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework Javadoc — PooledDataBuffer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/PooledDataBuffer.html)
- [Spring Framework Javadoc — DataBufferUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework Javadoc — NettyDataBuffer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/buffer/NettyDataBuffer.html)
- [Netty — Reference counted objects and ByteBuf lifecycle](https://netty.io/wiki/reference-counted-objects.html)
- [Netty API — ByteBuf retain, release and touch](https://netty.io/4.1/api/io/netty/buffer/ByteBuf.html)
