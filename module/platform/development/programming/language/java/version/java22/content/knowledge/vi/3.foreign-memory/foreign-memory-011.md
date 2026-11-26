# An toàn biên, an toàn vòng đời và giới hạn truy cập theo luồng

Foreign Function & Memory API (FFM) cung cấp cách làm việc với bộ nhớ ngoài heap và gọi mã native bằng các kiểu dữ liệu Java có cấu trúc. API này được hoàn thiện trong JDK 22 qua JEP 454 và tiếp tục là API chuẩn trong Java hiện đại. Khi sử dụng FFM, ba câu hỏi an toàn cần được trả lời rõ ràng: một thao tác được phép truy cập bao nhiêu byte, vùng nhớ còn sống trong bao lâu và thread nào được phép truy cập vùng nhớ đó.

Ba câu hỏi này tương ứng với ba cơ chế cốt lõi của API:

- **An toàn biên (spatial safety):** `MemorySegment` giới hạn vùng byte mà thao tác đọc hoặc ghi được phép truy cập.
- **An toàn vòng đời (temporal safety):** `Arena` quản lý thời điểm vùng nhớ được tạo và giải phóng; segment hết hiệu lực khi arena đóng.
- **Giới hạn truy cập theo luồng (thread confinement):** arena xác định segment chỉ được truy cập từ một thread hay có thể được chia sẻ giữa nhiều thread.

Các ví dụ trong bài dùng API chính thức thuộc package `java.lang.foreign`, có thể biên dịch với JDK 22 trở lên mà không cần bật preview cho FFM.

## 1. Mối quan hệ giữa MemorySegment và Arena

`MemorySegment` là một vùng nhớ có kích thước xác định. Segment có thể đại diện cho vùng nhớ native, một phần của heap array, buffer hoặc vùng nhớ ánh xạ từ file. API cung cấp thông tin về kích thước và kiểm tra các thao tác truy cập dựa trên ranh giới của segment.

`Arena` quản lý vòng đời của những segment được cấp phát từ nó. Khi arena đóng, các segment gắn với arena đó không còn được phép truy cập. Vì vậy, segment và arena cần được xem là một cặp: segment là vùng nhớ cần sử dụng, arena là chủ sở hữu vòng đời của vùng nhớ.

`MemoryLayout` và các `ValueLayout` mô tả cách diễn giải dữ liệu trong segment, bao gồm kích thước, kiểu giá trị, thứ tự byte và căn chỉnh. Dùng layout giúp mã thể hiện ý định rõ ràng và tránh tự tính toán kích thước theo các hằng số rời rạc.

| Thành phần | Trách nhiệm |
| --- | --- |
| `MemorySegment` | Biểu diễn vùng nhớ có kích thước và cung cấp thao tác đọc, ghi, cắt lát. |
| `Arena` | Cấp phát bộ nhớ và kiểm soát thời điểm segment còn hiệu lực. |
| `MemoryLayout` | Mô tả cấu trúc, kích thước và căn chỉnh của vùng dữ liệu. |
| `ValueLayout` | Mô tả một giá trị đơn như `JAVA_INT`, `JAVA_LONG` hoặc `JAVA_BYTE`. |

## 2. An toàn biên: giới hạn vùng byte được truy cập

Mỗi `MemorySegment` có `byteSize()` xác định. Khi đọc hoặc ghi, API kiểm tra vùng byte mà layout yêu cầu có nằm hoàn toàn bên trong segment hay không. Nếu thao tác vượt khỏi biên, API ném `IndexOutOfBoundsException` thay vì cho phép mã Java đọc hoặc ghi tùy ý sang vùng nhớ kế bên.

Ví dụ sau cấp phát 16 byte, ghi một số nguyên ở offset 0 và tạo một slice chỉ bao gồm 4 byte đầu tiên:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentBoundsExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(16, 8);

            segment.set(ValueLayout.JAVA_INT, 0, 2026);
            int year = segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println(year);

            MemorySegment firstInt = segment.asSlice(
                    0, ValueLayout.JAVA_INT.byteSize());
            System.out.println(firstInt.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
```

`asSlice(offset, size)` tạo một segment mới cùng tham chiếu tới vùng nhớ gốc nhưng có biên nhỏ hơn. Trong ví dụ, `firstInt` chỉ cho phép truy cập 4 byte đầu. Slice không sao chép dữ liệu và vẫn phụ thuộc vào vòng đời của arena đã cấp phát segment gốc.

Có thể thấy kiểm tra biên bằng một offset hợp lệ về căn chỉnh nhưng vượt quá kích thước segment:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16, 8);

    try {
        // Offset 16 nằm ngay sau segment; một int cần thêm 4 byte.
        segment.get(ValueLayout.JAVA_INT, 16);
    } catch (IndexOutOfBoundsException ex) {
        System.out.println("Truy cập vượt biên đã bị từ chối");
    }
}
```

Layout tham gia vào phép kiểm tra: thao tác phải có đủ số byte cho kiểu dữ liệu được đọc hoặc ghi. Khi thiết kế cấu trúc phức tạp, nên mô tả cấu trúc bằng `MemoryLayout` thay vì tự suy luận offset và kích thước ở nhiều nơi.

## 3. An toàn vòng đời: segment chỉ hợp lệ khi arena còn mở

Native memory không được thu hồi theo cơ chế garbage collection thông thường của object Java. Nếu cấp phát native memory rồi quên giải phóng, tiến trình có thể tiêu thụ bộ nhớ ngoài heap ngày càng nhiều. Nếu giải phóng quá sớm, mã có thể tiếp tục dùng một vùng nhớ không còn hợp lệ.

`Arena` giải quyết vấn đề vòng đời bằng một ranh giới sở hữu rõ ràng. Với arena có thể đóng, gọi `close()` sẽ kết thúc hiệu lực của các segment thuộc arena. `try`-with-resources là cách phổ biến để bảo đảm arena được đóng kể cả khi tác vụ ném exception:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SegmentLifetimeExample {
    public static void main(String[] args) {
        MemorySegment segment;

        try (Arena arena = Arena.ofConfined()) {
            segment = arena.allocate(ValueLayout.JAVA_LONG);
            segment.set(ValueLayout.JAVA_LONG, 0, 9_000_000_000L);
            System.out.println(segment.get(ValueLayout.JAVA_LONG, 0));
        }

        // Arena đã đóng: segment không còn được phép truy cập.
        try {
            segment.get(ValueLayout.JAVA_LONG, 0);
        } catch (IllegalStateException ex) {
            System.out.println("Segment đã hết hiệu lực");
        }
    }
}
```

Sau khi `arena.close()` hoàn tất, thao tác truy cập segment sẽ thất bại bằng `IllegalStateException`. Việc đóng arena cũng giải phóng tài nguyên native do arena quản lý. Đây là bảo vệ theo thời gian: ngay cả khi offset nằm trong biên, truy cập vẫn bị từ chối nếu vùng nhớ đã hết vòng đời.

Một lỗi thiết kế thường gặp là trả về segment được cấp phát bên trong một arena cục bộ đã đóng:

```java
// Không dùng mẫu này: segment được trả về sau khi arena đã đóng.
static MemorySegment createInvalidSegment() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(64, 8);
    }
}
```

Nếu segment cần sống lâu hơn phương thức tạo nó, hãy để bên gọi sở hữu arena và truyền arena vào phương thức cấp phát:

```java
static MemorySegment allocateBuffer(Arena arena, long size) {
    return arena.allocate(size, 8);
}

public static void main(String[] args) {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment buffer = allocateBuffer(arena, 64);
        // buffer còn hợp lệ trong phạm vi arena.
    }
}
```

Quy tắc sở hữu này giúp người đọc xác định được ai chịu trách nhiệm đóng vùng nhớ và segment có thể được dùng tới thời điểm nào.

## 4. Giới hạn truy cập theo luồng

Việc một segment còn sống và offset hợp lệ chưa đủ để cho phép mọi thread truy cập nó. Arena còn quy định khả năng truy cập theo thread. FFM cung cấp các kiểu arena phù hợp với những mô hình sử dụng khác nhau:

| Cách tạo arena | Thread được truy cập segment | Quản lý vòng đời |
| --- | --- | --- |
| `Arena.ofConfined()` | Chỉ thread tạo arena. | Đóng tường minh; thông thường đóng trong `try`-with-resources trên thread sở hữu. |
| `Arena.ofShared()` | Có thể truy cập từ nhiều thread. | Đóng tường minh; cần bảo đảm các thread dùng segment đã hoàn tất trước khi đóng. |
| `Arena.ofAuto()` | Có thể truy cập từ nhiều thread. | Thu hồi tự động theo khả năng thu gom của GC; thời điểm thu hồi không xác định. |
| `Arena.global()` | Có thể truy cập từ nhiều thread. | Vòng đời toàn tiến trình; không đóng được. |

### Arena confined

`Arena.ofConfined()` là lựa chọn phù hợp cho cấp phát cục bộ trong một tác vụ đồng bộ. Segment do arena này tạo ra chỉ được truy cập từ thread sở hữu arena. Nếu một thread khác cố đọc hoặc ghi segment, API ném `WrongThreadException`.

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.WrongThreadException;

public class ThreadConfinementExample {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 22);

            Thread worker = Thread.ofPlatform().start(() -> {
                try {
                    segment.get(ValueLayout.JAVA_INT, 0);
                } catch (WrongThreadException ex) {
                    System.out.println("Thread khác không được truy cập segment này");
                }
            });

            worker.join();
        }
    }
}
```

Ví dụ giữ arena mở cho tới khi `worker.join()` hoàn tất. Lỗi trong ví dụ là do thread không có quyền truy cập segment, không phải do segment đã bị đóng.

### Arena shared

Khi nhiều thread thực sự cần truy cập cùng vùng native memory, dùng `Arena.ofShared()`:

```java
try (Arena arena = Arena.ofShared()) {
    MemorySegment sharedSegment = arena.allocate(ValueLayout.JAVA_INT);
    // Có thể truyền sharedSegment cho các thread khác trong phạm vi này.
    // Chỉ đóng arena sau khi tất cả thread sử dụng segment đã hoàn tất.
}
```

Shared arena cho phép truy cập từ nhiều thread; nó không tự biến dữ liệu thành thread-safe. Nếu nhiều thread cùng ghi một vùng nhớ, ứng dụng vẫn phải dùng khóa, cơ chế đồng bộ hoặc cách phối hợp phù hợp để tránh race condition. Khả năng truy cập chéo thread và tính nguyên tử của thao tác dữ liệu là hai vấn đề khác nhau.

## 5. Chọn arena theo vòng đời và mô hình thực thi

Trong ứng dụng thực tế, lựa chọn arena nên xuất phát từ câu hỏi ai dùng segment và ai quyết định thời điểm giải phóng:

- **Tác vụ ngắn, chạy trên một thread:** ưu tiên `Arena.ofConfined()` và `try`-with-resources. Đây thường là lựa chọn đơn giản, có thời điểm giải phóng xác định và có giới hạn truy cập rõ ràng.
- **Tác vụ được chia sẻ giữa nhiều thread:** dùng `Arena.ofShared()`. Chủ sở hữu cần chờ các tác vụ kết thúc trước khi đóng arena.
- **Dữ liệu có vòng đời gắn với khả năng được GC thu gom:** `Arena.ofAuto()` cho phép thu hồi tự động, nhưng không thích hợp khi ứng dụng cần giải phóng native memory tại một thời điểm chính xác.
- **Dữ liệu có chủ đích tồn tại suốt tiến trình:** `Arena.global()` có thể phù hợp với dữ liệu dùng chung có vòng đời toàn ứng dụng. Không dùng nó cho cấp phát tạm thời vì không thể đóng arena để thu hồi sớm.

`Arena.ofAuto()` và `Arena.global()` không phải cơ chế thay thế cho việc quản lý vòng đời tường minh. Đối với buffer native có kích thước đáng kể hoặc tài nguyên cần giải phóng ngay sau một thao tác, arena có thể đóng thường giúp kiểm soát bộ nhớ dễ dự đoán hơn.

## 6. Những giới hạn an toàn cần hiểu đúng

Các kiểm tra của FFM bảo vệ những thao tác được thực hiện thông qua `MemorySegment`, nhưng không thể biến mã native thành mã an toàn tuyệt đối. Khi gọi thư viện native, ứng dụng vẫn cần bảo đảm hợp đồng giữa Java và native chính xác:

1. **Kích thước phải đúng với vùng nhớ thật.** Nếu khai báo segment lớn hơn vùng cấp phát thực tế, một thao tác nằm trong biên segment vẫn có thể chạm vào địa chỉ không hợp lệ. FFM không thể tự suy ra kích thước thật của một con trỏ tùy ý.
2. **Layout phải khớp ABI và cấu trúc native.** Sai kiểu dữ liệu, thứ tự byte, căn chỉnh hoặc offset có thể khiến thư viện native diễn giải sai dữ liệu.
3. **Native code có thể truy cập bộ nhớ ngoài các kiểm tra của Java.** Một hàm C/C++ nhận con trỏ có thể ghi vượt biên hoặc giữ con trỏ sau khi arena đóng. Java không thể tự ngăn thư viện bên ngoài vi phạm hợp đồng đó.
4. **Shared memory vẫn cần đồng bộ.** Arena shared chỉ nới quyền truy cập giữa các thread; nó không tự cung cấp khóa, thứ tự bộ nhớ hay tính nguyên tử cho các thao tác đọc/ghi.
5. **Không đóng arena khi tác vụ còn sử dụng segment.** Đặc biệt với tác vụ bất đồng bộ, phải quản lý việc hoàn tất hoặc hủy tác vụ trước khi giải phóng vùng nhớ.

Vì vậy, hãy giữ phần tương tác native ở một lớp có trách nhiệm rõ ràng, dùng layout mô tả dữ liệu, giới hạn segment ở kích thước đã biết và quản lý arena theo vòng đời của tác vụ.

## 7. Checklist thiết kế an toàn

- Cấp phát qua `Arena` và chọn loại arena dựa trên mô hình thread thực tế.
- Dùng `ValueLayout` hoặc `MemoryLayout` phù hợp với dữ liệu cần đọc, ghi.
- Dùng `asSlice` để truyền cho từng thành phần chỉ vùng nhớ mà thành phần đó cần.
- Dùng `try`-with-resources cho arena có vòng đời hữu hạn.
- Không trả về hoặc lưu segment sau khi arena sở hữu nó đã đóng.
- Với shared arena, chờ mọi tác vụ sử dụng segment hoàn tất rồi mới đóng.
- Tự đồng bộ dữ liệu nếu nhiều thread cùng đọc/ghi vùng nhớ có thể thay đổi.
- Xác minh kích thước, layout, alignment và vòng đời con trỏ ở biên giao tiếp với thư viện native.

Khi ba điều kiện về biên, vòng đời và thread được thiết kế cùng nhau, `MemorySegment` giúp mã Java làm việc với native memory có kiểm soát hơn. Các kiểm tra này giảm đáng kể lỗi truy cập bộ nhớ trong phần Java, trong khi hợp đồng với thư viện native vẫn phải được thiết kế và xác minh cẩn thận.

## Tài liệu tham khảo

- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454) — API được hoàn thiện trong JDK 22.
- [Arena, Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html) — các loại arena, cấp phát và quản lý vòng đời.
- [MemorySegment, Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html) — kích thước, slice và thao tác truy cập segment.
- [MemoryLayout, Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html) — mô tả cấu trúc và căn chỉnh bộ nhớ.
- [ValueLayout, Java SE 22 API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html) — layout cho các giá trị nguyên thủy Java.
