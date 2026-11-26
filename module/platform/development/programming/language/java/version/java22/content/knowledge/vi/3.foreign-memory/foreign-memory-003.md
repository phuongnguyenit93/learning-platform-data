# Arena.ofConfined, Arena.ofShared, Arena.ofAuto và Arena.global: quyền sở hữu và vòng đời

## 1. Arena quản lý điều gì?

Foreign Function and Memory API (FFM API) cho phép Java làm việc với vùng nhớ nằm ngoài heap của JVM thông qua `MemorySegment`. Khi cấp phát native memory, chương trình cần xác định vùng nhớ tồn tại trong bao lâu và thread nào được phép truy cập. `Arena` giải quyết hai vấn đề đó.

`Arena` thuộc package `java.lang.foreign`, đồng thời triển khai `SegmentAllocator` và `AutoCloseable`. Mỗi arena có một scope; các `MemorySegment` được cấp phát từ arena gắn với scope này. Arena quyết định thời điểm scope còn hiệu lực, quy tắc truy cập theo thread và cách giải phóng vùng nhớ nền.

JEP 454 hoàn thiện Foreign Function and Memory API trong Java 22. Vì vậy, các ví dụ ở bài này sử dụng API chính thức từ Java 22 trở lên, không cần bật preview. Tài liệu Oracle ở các phiên bản Java hiện hành vẫn sử dụng bốn cách tạo arena dưới đây.

## 2. So sánh bốn loại arena

| Loại arena | Tạo bằng | Quyền truy cập segment | Ai giải phóng vùng nhớ? | Có thể gọi `close()`? |
|---|---|---|---|---|
| Confined | `Arena.ofConfined()` | Chỉ owner thread | Owner thread chủ động đóng | Có, chỉ owner thread |
| Shared | `Arena.ofShared()` | Bất kỳ thread nào | Một thread chủ động đóng | Có, bất kỳ thread nào |
| Automatic | `Arena.ofAuto()` | Bất kỳ thread nào | Garbage Collector, sau khi arena và các segment không còn reachable | Không; ném `UnsupportedOperationException` |
| Global | `Arena.global()` | Bất kỳ thread nào | Không giải phóng trong vòng đời tiến trình | Không; ném `UnsupportedOperationException` |

Hai lựa chọn `ofConfined()` và `ofShared()` có vòng đời hữu hạn do chương trình quản lý. `ofAuto()` cũng có vòng đời hữu hạn, nhưng thời điểm thu hồi do GC quyết định. `global()` có vòng đời không giới hạn và vùng nhớ được cấp phát từ đó không được thu hồi.

## 3. Arena.ofConfined(): một thread sở hữu và đóng arena

`Arena.ofConfined()` tạo một arena gắn với thread gọi phương thức tạo. Thread này là *owner thread*. Chỉ owner thread được truy cập các segment thuộc arena và chỉ owner thread được đóng arena.

Đây là lựa chọn phù hợp khi vùng nhớ chỉ được dùng trong một tác vụ đồng bộ trên một thread. Có thể kết hợp với `try-with-resources` để bảo đảm vùng nhớ được giải phóng khi rời khỏi khối:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ConfinedExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocate(
                    2L * Integer.BYTES,
                    Integer.BYTES);

            numbers.set(ValueLayout.JAVA_INT, 0, 10);
            numbers.set(ValueLayout.JAVA_INT, Integer.BYTES, 20);

            int first = numbers.get(ValueLayout.JAVA_INT, 0);
            int second = numbers.get(ValueLayout.JAVA_INT, Integer.BYTES);
            System.out.println(first + second); // 30
        }
        // Arena được đóng ở đây; native memory được giải phóng.
    }
}
```

Khi `try` kết thúc, `close()` được gọi. Scope của arena hết hiệu lực và tất cả segment gắn với scope đó bị vô hiệu hóa. Nếu vẫn giữ một tham chiếu `MemorySegment` rồi truy cập sau khi arena đã đóng, thao tác truy cập sẽ thất bại với `IllegalStateException`.

Nếu thread khác cố truy cập segment của confined arena hoặc cố đóng arena, Java báo `WrongThreadException`. Vì thế, không truyền segment của confined arena cho một tác vụ chạy trên thread khác.

## 4. Arena.ofShared(): nhiều thread cùng truy cập

`Arena.ofShared()` tạo arena không có owner thread. Các segment được cấp phát từ arena có thể được truy cập bởi bất kỳ thread nào. Bất kỳ thread nào cũng có thể gọi `close()`; việc đóng shared arena được bảo đảm an toàn và nguyên tử.

Ví dụ dưới đây ghi dữ liệu trên thread hiện tại, chuyển segment cho tác vụ bất đồng bộ đọc, rồi chờ tác vụ hoàn tất trước khi đóng arena:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.CompletableFuture;

public class SharedExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment value = arena.allocate(
                    Integer.BYTES,
                    Integer.BYTES);

            value.set(ValueLayout.JAVA_INT, 0, 42);

            CompletableFuture<Integer> result = CompletableFuture.supplyAsync(
                    () -> value.get(ValueLayout.JAVA_INT, 0));

            System.out.println(result.join()); // 42
        }
        // Tác vụ đã hoàn tất trước khi arena bị đóng.
    }
}
```

`ofShared()` giải quyết quyền truy cập xuyên thread và cho phép quản lý vòng đời tường minh. Nó không tự đồng bộ hóa dữ liệu mà các thread cùng đọc hoặc ghi. Nếu nhiều thread có thể cập nhật cùng một vùng nhớ, chương trình vẫn phải thiết kế cơ chế đồng bộ phù hợp để tránh race condition và bảo đảm thứ tự nhìn thấy dữ liệu.

Chỉ đóng arena sau khi các thao tác sử dụng segment đã hoàn tất. Nếu một segment đang được truy cập đồng thời trong một số thao tác native, `close()` có thể thất bại với `IllegalStateException`; việc segment có thể được truy cập từ nhiều thread không có nghĩa là có thể thu hồi nó trong khi thao tác vẫn đang chạy.

## 5. Arena.ofAuto(): để Garbage Collector quản lý thời điểm thu hồi

`Arena.ofAuto()` tạo một arena có vòng đời do Garbage Collector quản lý. Các segment thuộc arena có thể được truy cập từ bất kỳ thread nào. Vùng nhớ nền được thu hồi tại một thời điểm không xác định sau khi arena và toàn bộ các segment được cấp phát từ arena không còn reachable.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class AutomaticExample {
    public static void main(String[] args) {
        MemorySegment data = Arena.ofAuto().allocate(
                Integer.BYTES,
                Integer.BYTES);

        data.set(ValueLayout.JAVA_INT, 0, 2026);
        System.out.println(data.get(ValueLayout.JAVA_INT, 0));

        // Khi data và các tham chiếu liên quan không còn reachable,
        // vùng nhớ có thể được GC thu hồi ở một thời điểm sau đó.
    }
}
```

Không thể gọi `close()` trên automatic arena; thao tác này ném `UnsupportedOperationException`. Do GC quyết định thời điểm thu hồi, chương trình không kiểm soát được chính xác lúc native memory được trả lại hệ điều hành. Vì vậy, automatic arena phù hợp với dữ liệu có vòng đời gắn với khả năng reachable của đối tượng Java và không yêu cầu giải phóng đúng một thời điểm cụ thể.

Không nên chọn `ofAuto()` chỉ vì muốn tránh viết `try-with-resources` cho vùng nhớ native lớn hoặc được cấp phát thường xuyên. Nếu ứng dụng cần giới hạn mức sử dụng native memory hoặc cần giải phóng ngay sau một tác vụ, hãy ưu tiên arena có thể đóng tường minh.

## 6. Arena.global(): vòng đời không giới hạn

`Arena.global()` trả về global arena dùng chung. Các segment được cấp phát từ arena này có thể được truy cập bởi bất kỳ thread nào, nhưng vùng nhớ nền không bao giờ được giải phóng trong vòng đời tiến trình. Gọi `close()` sẽ ném `UnsupportedOperationException`.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

public class GlobalExample {
    // Segment tồn tại trong vòng đời tiến trình.
    private static final MemorySegment SHARED_BLOCK =
            Arena.global().allocate(256, 8);

    public static MemorySegment sharedBlock() {
        return SHARED_BLOCK;
    }
}
```

Global arena có thể dùng cho dữ liệu native nhỏ, thực sự cần tồn tại lâu dài và được chia sẻ xuyên thread. Không dùng nó cho dữ liệu tăng theo request, file lớn, buffer tạm hoặc vùng nhớ cần được giải phóng khi một tác vụ hoàn tất. Những vùng nhớ đó sẽ tích lũy cho đến khi tiến trình kết thúc.

## 7. Điều gì xảy ra khi đóng arena?

Với confined và shared arena, `close()` kết thúc scope. Sau khi đóng thành công:

1. Mọi `MemorySegment` gắn với scope đó không còn hợp lệ để truy cập.
2. Các vùng native memory nền được giải phóng.
3. Những lần truy cập segment đã bị vô hiệu hóa sẽ thất bại với `IllegalStateException`.
4. Gọi `close()` lần thứ hai cũng thất bại với `IllegalStateException`; thao tác đóng arena không có tính idempotent.

Có thể kiểm tra trạng thái scope bằng `arena.scope().isAlive()`, nhưng thông thường nên quản lý vòng đời bằng `try-with-resources` để phạm vi sử dụng segment khớp với phạm vi sống của arena.

Ví dụ sau minh họa lỗi truy cập sau khi đóng:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ClosedArenaExample {
    public static void main(String[] args) {
        MemorySegment data;

        try (Arena arena = Arena.ofConfined()) {
            data = arena.allocate(Integer.BYTES, Integer.BYTES);
            data.set(ValueLayout.JAVA_INT, 0, 7);
        }

        // Scope đã đóng; thao tác này ném IllegalStateException.
        System.out.println(data.get(ValueLayout.JAVA_INT, 0));
    }
}
```

Đối với confined arena, `close()` phải chạy trên owner thread. Đối với shared arena, bất kỳ thread nào cũng có thể đóng. Đối với automatic và global arena, không có thao tác đóng tường minh được hỗ trợ.

## 8. Chọn arena theo vòng đời và quyền sở hữu

| Nhu cầu của ứng dụng | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Một tác vụ xử lý native memory trên một thread | `Arena.ofConfined()` | Quyền sở hữu đơn giản, giải phóng xác định bằng `close()`. |
| Nhiều thread cần truy cập chung một segment | `Arena.ofShared()` | Không giới hạn owner thread, có thể đóng tường minh khi các tác vụ hoàn tất. |
| Vùng nhớ có vòng đời theo reachability và không cần giải phóng đúng thời điểm | `Arena.ofAuto()` | GC tự quản lý thu hồi, segment truy cập được từ nhiều thread. |
| Vùng nhớ nhỏ cần tồn tại đến khi tiến trình kết thúc | `Arena.global()` | Vòng đời không giới hạn, truy cập được từ mọi thread. |

Một số nguyên tắc thực tế:

- Bắt đầu với `Arena.ofConfined()` nếu segment chỉ dùng trong một tác vụ đồng bộ. Đây là lựa chọn dễ kiểm soát và thường có chi phí quản lý thấp hơn shared arena.
- Chỉ dùng `Arena.ofShared()` khi cần chia sẻ segment giữa nhiều thread. Hãy chờ các tác vụ kết thúc trước khi đóng arena.
- Chọn `Arena.ofAuto()` khi chấp nhận việc GC thu hồi ở thời điểm không xác định; đừng dựa vào nó để đáp ứng yêu cầu giải phóng native memory tức thời.
- Dùng `Arena.global()` rất tiết chế vì không thể thu hồi vùng nhớ đã cấp phát trước khi tiến trình kết thúc.
- Không truy cập segment sau khi scope đã hết hiệu lực và không để native code giữ địa chỉ bộ nhớ vượt quá vòng đời arena sở hữu vùng nhớ đó.

## 9. Phạm vi API áp dụng hiện nay

Foreign Function and Memory API trở thành API chính thức trong Java 22 thông qua JEP 454. Các phương thức được dùng trong bài là `Arena.ofConfined()`, `Arena.ofShared()`, `Arena.ofAuto()` và `Arena.global()` trong package `java.lang.foreign`.

Các ví dụ không dùng tên API từ những vòng preview cũ của FFM như `Arena.openConfined()`, `Arena.openShared()` hoặc `ResourceScope`. Khi làm việc với dự án Java hiện đại, hãy theo API `Arena` và `MemorySegment` đã được chuẩn hóa, đồng thời kiểm tra phiên bản JDK mục tiêu của dự án.

## 10. Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — trạng thái và mục tiêu của API được hoàn thiện trong Java 22.
- [Java SE 22 API: Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html) — đặc tả các phương thức tạo arena, scope và quy tắc đóng.
- [Java SE 26 API: Arena](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/Arena.html) — API hiện hành, gồm quyền truy cập theo thread và vòng đời từng loại arena.
- [Oracle Java SE 25: Memory Segments and Arenas](https://docs.oracle.com/en/java/javase/25/core/memory-segments-and-arenas.html) — hướng dẫn thực hành cấp phát, truy cập và giải phóng native memory.
