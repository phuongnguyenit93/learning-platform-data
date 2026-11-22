# Tạo lát cắt asSlice và quan hệ chia sẻ dữ liệu với segment gốc

## Mục tiêu của bài

**MemorySegment.asSlice(...)** tạo một **lát cắt (slice)**: một đối tượng **MemorySegment** mới biểu diễn **một vùng con** trong cùng vùng nhớ đã được segment gốc quản lý. Đây là một **view không sao chép dữ liệu**. Khi hai view đều cho phép ghi, sửa cùng vị trí bằng view này sẽ được view kia nhìn thấy, miễn là quyền truy cập, vòng đời và quy tắc đồng bộ được đáp ứng.

Sau bài học, bạn có thể:

1. Phân biệt **segment gốc**, **slice**, **backing memory** và **bản sao độc lập**.
2. Dùng các overload **asSlice(offset)**, **asSlice(offset, byteSize)**, **asSlice(offset, byteSize, byteAlignment)** và **asSlice(offset, MemoryLayout)** đúng đơn vị **byte**.
3. Tính chính xác vị trí tương ứng giữa slice và root, kể cả **slice lồng nhau**.
4. Giải thích vì sao sửa qua slice ảnh hưởng segment gốc, mảng heap hoặc vùng nhớ native.
5. Phân biệt giới hạn không gian, alignment, read-only, thread confinement và thời gian sống của **Arena**.
6. Thiết kế xử lý gói tin, record, vùng header/payload hay dữ liệu native mà không tự gây lỗi out-of-bounds, use-after-close hoặc data race.

**Phiên bản:** Ví dụ hoàn chỉnh sử dụng **java.lang.foreign.MemorySegment** và **Arena** trên **JDK 22+**, nơi Foreign Function & Memory (FFM) API đã được chuẩn hóa (JEP 454). JDK 17 sử dụng API **incubator** khác; JDK 21 dùng API **preview** và có thể cần cờ preview, vì vậy **không** sao chép nguyên xi các chương trình dưới đây sang JDK 17/21. Mã minh họa dưới đây biên dịch với Java 22 trở lên mà **không cần --enable-preview** cho các thao tác bộ nhớ được sử dụng.

## 1. MemorySegment biểu diễn gì?

Một **MemorySegment** là một view có giới hạn đối với một vùng byte liên tục. Nó có những đặc điểm cần nhớ:

| Đặc điểm | Ý nghĩa với asSlice |
| --- | --- |
| **Backing memory** | Những byte thực sự đang được biểu diễn, ở Java heap hoặc native memory |
| **address()** | Địa chỉ/độ lệch logic của segment; slice bắt đầu ở địa chỉ gốc cộng offset |
| **byteSize()** | Số **byte** mà view cho phép truy cập; slice có kích thước riêng |
| **scope()** | Phạm vi thời gian sống: slice dùng **cùng scope** với segment gốc |
| **isReadOnly()** | Trạng thái chỉ đọc: slice của view chỉ đọc vẫn chỉ đọc |
| **isAccessibleBy(thread)** | Thread nào có thể truy cập: slice không nới lỏng ràng buộc thread |
| **isNative()** | Đang biểu diễn native memory hay không; slicing không biến heap thành native hoặc ngược lại |

**Heap segment** có thể được tạo bằng **MemorySegment.ofArray(byte[])**, **ofArray(int[])** và các overload tương ứng: nó được hỗ trợ bởi mảng Java. **Native segment** có thể được cấp bởi **Arena.allocate(...)**: nó biểu diễn bộ nhớ ngoài Java heap. Cả hai có thể được chia thành nhiều lát cắt; semantics **không copy**, giới hạn byte và liên kết với backing memory tương tự nhau.

Một **MemorySegment object** không phải là bản thân vùng nhớ. Khi gọi **asSlice**, bạn tạo một đối tượng mô tả phạm vi khác trên **cùng các byte**, chứ không tạo một allocation độc lập.

## 2. Hình dung slice trên một vùng 10 byte

Giả sử segment gốc có **byteSize() == 10** và ta gọi:

~~~java
MemorySegment slice = root.asSlice(3, 4);
~~~

Hình dung các offset:

~~~text
root (10 byte):
offset root    0  1  2 |3  4  5  6| 7  8  9
              ----------+-----------+---------
backing data   A  B  C |D  E  F  G| H  I  J
                        ^           ^
                      slice       end-exclusive

slice (4 byte):
offset slice             0  1  2  3
backing data             D  E  F  G

root offset = 3 + slice offset
~~~

**root[3]** và **slice[0]** chỉ đến **cùng byte**. Nếu sửa **slice[1]**, đó là byte **root[4]**. Nếu sửa **root[6]**, đọc **slice[3]** sẽ thấy giá trị mới.

Điều được thay đổi bởi **asSlice(3, 4)** là **phạm vi được phép truy cập**: slice chỉ nhìn thấy 4 byte (root offsets 3–6). Không có mảng dữ liệu mới dài 4 byte được copy từ root.

Ba điều không được nhầm:

- **View mới** không đồng nghĩa **vùng nhớ mới**.
- **Độ lệch của slice** bắt đầu lại từ **0**, không phải từ **3**.
- **Giới hạn slice** không thay đổi **kích thước hay nội dung** của root; root vẫn chứa đủ 10 byte.

## 3. Các overload asSlice và cách tính kích thước

Trong JDK 22+, các dạng quan trọng là:

~~~java
MemorySegment tail = root.asSlice(offset);
MemorySegment part = root.asSlice(offset, newSize);
MemorySegment aligned = root.asSlice(offset, newSize, byteAlignment);
MemorySegment typed = root.asSlice(offset, layout);
~~~

| Overload | Ý nghĩa |
| --- | --- |
| **asSlice(long offset)** | View từ **offset** đến hết segment. Kích thước = **root.byteSize() - offset** |
| **asSlice(long offset, long newSize)** | View bắt đầu ở **offset**, dài **newSize byte** |
| **asSlice(long offset, long newSize, long byteAlignment)** | Tạo view có ràng buộc alignment được chỉ định, đồng thời kiểm tra địa chỉ bắt đầu phù hợp |
| **asSlice(long offset, MemoryLayout layout)** | Kích thước = **layout.byteSize()**, alignment = **layout.byteAlignment()** |

Các tham số **offset**, **newSize**, **byteAlignment** đều có đơn vị **byte**, không phải số phần tử Java, số lượng int, hoặc chỉ số trong một mảng object. Với **ValueLayout.JAVA_INT**, một giá trị **int** chiếm **4 byte**; muốn bắt đầu ở phần tử int thứ 2 (đếm từ 0) thì offset là **8**, không phải **2**.

Các điều kiện cơ bản cho **asSlice(offset, newSize)** với segment dài **N** byte là:

~~~text
0 <= offset <= N
0 <= newSize <= N - offset
~~~

Viết bằng lời: **offset không âm**, **newSize không âm**, và **phần cuối của slice không được vượt quá phần cuối của segment nguồn**. Vi phạm có thể gây **IndexOutOfBoundsException**. Công thức **newSize <= N - offset** cũng giúp tránh cộng hai số lớn dễ bị overflow trong các bước kiểm tra do ứng dụng tự viết.

**Biên hợp lệ đặc biệt:**

~~~java
MemorySegment empty = root.asSlice(root.byteSize(), 0);
~~~

Đây là **slice 0 byte** tại cuối root, tạo view hợp lệ nhưng không thể đọc một byte tại offset 0. **root.asSlice(root.byteSize())** cũng cho một slice trống. Trường hợp này hữu ích khi biểu diễn dữ liệu không có payload; không nên xử lý nó như một con trỏ tùy ý có thể dereference.

Đối với dạng alignment:

- **byteAlignment** phải là một lũy thừa của 2 và lớn hơn 0; giá trị không hợp lệ gây **IllegalArgumentException**.
- Địa chỉ bắt đầu **root.address() + offset** phải thỏa alignment, nếu không có thể có **IllegalArgumentException**.
- Dạng **asSlice(offset, layout)** tương đương yêu cầu cả **layout.byteSize()** và **layout.byteAlignment()**.
- Dạng hai tham số **asSlice(offset, newSize)** không đồng nghĩa mọi kiểu đọc đều aligned; bước **get/set** với **ValueLayout** vẫn kiểm tra alignment tương ứng.

Đừng tự gán byteAlignment bằng kích thước gói tin; alignment là yêu cầu về **địa chỉ bắt đầu**, không phải bắt buộc slice dài bao nhiêu byte.

## 4. Ví dụ runnable 1: heap slice và mảng Java chia sẻ cùng dữ liệu

### File SliceHeapDemo.java

~~~java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public class SliceHeapDemo {
    public static void main(String[] args) {
        byte[] bytes = {10, 20, 30, 40, 50, 60};

        // Segment bao phủ toàn bộ byte[] Java.
        MemorySegment root = MemorySegment.ofArray(bytes);

        // Slice từ byte index 2, lấy 3 byte (index 2, 3, 4).
        MemorySegment middle = root.asSlice(2, 3);

        System.out.println("root size: " + root.byteSize());
        System.out.println("slice size: " + middle.byteSize());
        System.out.println("slice[0] first: "
                + middle.get(ValueLayout.JAVA_BYTE, 0));

        // Viết qua slice; mảng gốc thay đổi ngay.
        middle.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);
        System.out.println("after slice write: "
                + Arrays.toString(bytes));

        // Viết qua root; slice nhìn thấy thay đổi ở vị trí tương ứng.
        root.set(ValueLayout.JAVA_BYTE, 4, (byte) 77);
        System.out.println("slice[2] after root write: "
                + middle.get(ValueLayout.JAVA_BYTE, 2));

        // Slice lồng trong middle: root index 3 và 4.
        MemorySegment nested = middle.asSlice(1, 2);
        nested.set(ValueLayout.JAVA_BYTE, 0, (byte) 88);
        System.out.println("after nested write: "
                + Arrays.toString(bytes));

        // Slice chỉ đọc vẫn thấy dữ liệu, nhưng không cho ghi qua view này.
        MemorySegment readOnly = middle.asReadOnly();
        System.out.println("read-only slice: " + readOnly.isReadOnly());
        System.out.println("read-only value: "
                + readOnly.get(ValueLayout.JAVA_BYTE, 0));

        try {
            readOnly.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
        } catch (IllegalArgumentException expected) {
            System.out.println("read-only write rejected");
        }
    }
}
~~~

Biên dịch và chạy trên **JDK 22+**:

~~~bash
javac SliceHeapDemo.java
java SliceHeapDemo
~~~

Stdout:

~~~text
root size: 6
slice size: 3
slice[0] first: 30
after slice write: [10, 20, 99, 40, 50, 60]
slice[2] after root write: 77
after nested write: [10, 20, 99, 88, 77, 60]
read-only slice: true
read-only value: 99
read-only write rejected
~~~

**Giải thích từng giá trị:**

- **root** có 6 byte vì **byte[]** ban đầu chứa 6 phần tử, mỗi phần tử 1 byte.
- **middle = root.asSlice(2, 3)** bao phủ ba vị trí **root[2]**, **root[3]**, **root[4]**. Do đó **middle[0]** ban đầu là **30**.
- **middle.set(..., 0, 99)** ghi trực tiếp vào **bytes[2]**. Không cần hàm **copyBack**, **commit** hay bất kỳ lần đồng bộ dữ liệu riêng biệt nào để cập nhật mảng gốc trong cùng thread.
- **root.set(..., 4, 77)** làm **middle.get(..., 2)** đọc được **77** vì hai view cùng trỏ tới byte thứ 4.
- **nested = middle.asSlice(1, 2)** bắt đầu từ **root[3]**. Viết vào **nested[0]** làm **bytes[3] = 88**.
- **middle.asReadOnly()** tạo view chỉ đọc của cùng vùng nhớ. Nó không tạo bản sao bất biến: dữ liệu có thể tiếp tục thay đổi nếu có một view ghi khác như **root**.
- Ghi qua read-only view gây exception; chương trình bắt đúng **IllegalArgumentException** của phương thức **set** cho read-only segment.

Ví dụ dùng **heap memory** nên không cần đóng **Arena**. Mảng Java và mọi slice của nó được quản lý theo vòng đời của Java heap/GC. Không dùng **MemorySegment.address()** của heap segment như địa chỉ C để truyền thẳng cho native code.

## 5. Bảng ánh xạ offset: từ root sang slice và slice lồng

Giả sử:

~~~java
MemorySegment a = root.asSlice(100, 40);
MemorySegment b = a.asSlice(12, 20);
MemorySegment c = b.asSlice(5, 4);
~~~

Thì offset đầu của các view, tính từ root là:

| View | Bắt đầu tính từ root | byteSize() | Khoảng byte của root |
| --- | ---: | ---: | --- |
| **root** | 0 | ít nhất 140 | Toàn bộ root |
| **a** | 100 | 40 | 100 đến 139 |
| **b** | 112 | 20 | 112 đến 131 |
| **c** | 117 | 4 | 117 đến 120 |

Chẳng hạn **c.get(ValueLayout.JAVA_BYTE, 2)** tương ứng byte **root[119]** vì:

~~~text
absoluteOffset = offset(a trong root)
               + offset(b trong a)
               + offset(c trong b)
               + offset đọc trong c)

               = 100 + 12 + 5 + 2
               = 119
~~~

Đây là **đoạn mã/giả định minh họa**, không độc lập để biên dịch vì chưa tạo **root** đủ lớn. Mọi giá trị tính offset ở đây mang đơn vị **byte**; dùng kiểu **long** cho offsets và kích thước khi gọi API.

**Mấu chốt:** sau khi lấy slice, mọi lời gọi **get/set** dựa trên **tọa độ tương đối của view hiện tại**. Nếu đang ở **c**, bạn chỉ truyền offset **2**, không truyền offset root **119**. Truyền offset root vào slice là lỗi phổ biến dẫn đến **IndexOutOfBoundsException**.

## 6. Slice có bảo vệ giới hạn riêng: bounds checking

Nếu **middle.byteSize() == 3**, các địa chỉ byte hợp lệ trong middle là **0**, **1**, **2**. Bạn không được vượt qua giới hạn middle chỉ vì root vẫn có đủ byte.

~~~java
MemorySegment root = MemorySegment.ofArray(
        new byte[] {10, 20, 30, 40, 50, 60});
MemorySegment slice = root.asSlice(2, 3);

// Hợp lệ: lấy byte cuối của slice, tức root offset 4.
byte last = slice.get(ValueLayout.JAVA_BYTE, 2);

// Không hợp lệ: slice offset 3 nằm ngoài slice (dù root có offset 5).
byte invalid = slice.get(ValueLayout.JAVA_BYTE, 3);
~~~

Đây là **fragment cố ý minh họa thao tác lỗi**; dòng cuối sẽ ném **IndexOutOfBoundsException** và không phải một chương trình được thiết kế để chạy hết. Để kiểm tra có chủ đích:

~~~java
try {
    slice.get(ValueLayout.JAVA_BYTE, 3);
} catch (IndexOutOfBoundsException expected) {
    System.out.println("slice bounds enforced");
}
~~~

Lý do: **asSlice** tạo một hợp đồng truy cập con. Mã xử lý header chỉ được truyền slice header có thể tránh vô tình đọc tiếp sang payload nếu mọi thao tác nằm trong API truy cập của slice.

Các ràng buộc được kiểm tra:

1. **Ràng buộc khi tạo slice**: offset/size phải nằm trong segment đầu vào.
2. **Ràng buộc khi đọc/ghi**: cả vùng chiếm bởi **ValueLayout** phải nằm trong slice. Đọc **JAVA_INT** cần đủ 4 byte kể từ offset truy cập.
3. **Ràng buộc alignment**: địa chỉ truy cập phù hợp layout (đề cập ở mục 10).
4. **Ràng buộc thời gian sống/thread/read-only**: không được bỏ qua bằng cách tạo slice nhỏ hơn.

**asSlice không phải thao tác mở rộng phạm vi.** Nếu muốn truy cập byte nằm ngoài slice, code sở hữu backing memory phải cung cấp view thích hợp, không được tự thay đổi kích thước bằng thủ thuật unsafe.

## 7. Ví dụ runnable 2: native memory và vòng đời Arena

Điểm khác giữa heap slice và native slice không phải ở việc chia sẻ dữ liệu: **cả hai đều dùng chung backing storage**. Điểm khác nằm ở quyền sở hữu và thời gian sống của vùng nhớ native.

### File SliceNativeDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SliceNativeDemo {
    public static void main(String[] args) {
        MemorySegment escapedSlice;

        try (Arena arena = Arena.ofConfined()) {
            // 4 giá trị int, 4 byte mỗi giá trị: 16 byte.
            // Đảm bảo base address aligned theo JAVA_INT.
            MemorySegment root = arena.allocate(
                    16, ValueLayout.JAVA_INT.byteAlignment());

            MemorySegment secondAndThird = root.asSlice(4, 8);

            // root offset 4 là int thứ hai.
            root.set(ValueLayout.JAVA_INT, 4, 100);
            System.out.println("slice[0] = "
                    + secondAndThird.get(ValueLayout.JAVA_INT, 0));

            // slice offset 4 ánh xạ tới root offset 8.
            secondAndThird.set(ValueLayout.JAVA_INT, 4, 777);
            System.out.println("root offset 8 = "
                    + root.get(ValueLayout.JAVA_INT, 8));

            System.out.println("slice size = "
                    + secondAndThird.byteSize());

            // Chỉ giữ Java reference để minh họa lỗi sau close.
            escapedSlice = secondAndThird;
        }

        // Arena đã đóng; vùng nhớ native không còn sống.
        try {
            escapedSlice.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("access after arena close rejected");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SliceNativeDemo.java
java SliceNativeDemo
~~~

Stdout khi thực thi trên JDK 22+:

~~~text
slice[0] = 100
root offset 8 = 777
slice size = 8
access after arena close rejected
~~~

Giải thích:

- **Arena.ofConfined()** có vòng đời rõ ràng và cho truy cập từ thread sở hữu.
- **arena.allocate(16, 4)** cấp 16 byte native với căn chỉnh 4 byte.
- **root.asSlice(4, 8)** là view trên các byte **4..11**. Nó **không** tự tạo allocation thứ hai.
- **secondAndThird.get(JAVA_INT, 0)** đọc từ **root offset 4** và nhận **100**.
- **secondAndThird.set(JAVA_INT, 4, 777)** ghi vào **root offset 8**.
- Khi kết thúc **try-with-resources**, **arena.close()** khiến scope hết hạn và giải phóng native memory do arena sở hữu. **Cả root lẫn mọi slice** đều không còn được phép truy cập.
- **escapedSlice** chỉ là một reference Java tới view đã hết hạn; việc còn giữ reference không giữ native memory của arena tiếp tục hợp lệ.

**Không có thao tác slice.close().** Tài nguyên được quản lý bởi arena/scope. Việc slice một segment native **không** cấp quyền sở hữu riêng cho người nhận slice, cũng không dời thời hạn đóng arena.

## 8. Scope: slice và root có cùng thời gian sống

Giả sử root được allocate trong một arena có scope **S**:

~~~text
Arena scope S (alive)
    |
    +-- root: native memory [0, N)
    |      |
    |      +-- slice A: [20, 40)
    |      |
    |      +-- slice B: [40, 60)
    |               |
    |               +-- nested slice C
    |
    +-- tất cả đều thuộc cùng scope S

arena.close()
    |
    +-- S không còn alive
    +-- root, A, B, C đều không được phép truy cập
~~~

Trong JDK 22, **root.scope()** và **slice.scope()** gắn cùng scope nguồn. Đây là điều kiện để các view không sử dụng một native allocation sau khi nó bị giải phóng. Nếu một API native đòi hỏi pointer còn sống sau khi phương thức của bạn trả về, **không** tạo slice rồi đóng arena và trao slice đó cho caller; phải thiết kế ownership, nơi lưu reference và thời điểm close từ đầu.

Một số arena thường gặp:

| Arena | Vòng đời/thỏa thuận truy cập | Hệ quả với slices |
| --- | --- | --- |
| **Arena.ofConfined()** | Scope do owner thread quản lý, đóng rõ ràng | Slices có cùng owner-thread restriction |
| **Arena.ofShared()** | Scope có thể dùng từ nhiều thread, đóng rõ ràng | Slices truy cập được từ nhiều thread, nhưng vẫn phải đồng bộ dữ liệu |
| **Arena.ofAuto()** | Scope được quản lý tự động bằng GC | Slices không có thời điểm close tường minh như confined/shared |
| **Arena.global()** | Scope toàn cục, không được đóng tường minh | Slices có scope global; dùng thận trọng với tài nguyên lâu dài |

Dù arena loại nào, **asSlice không thay đổi tính chất lifecycle của backing memory**. Heap segment từ **MemorySegment.ofArray(...)** không được giải phóng bằng **Arena.close()**; mảng Java do GC quản lý.

## 9. Thread confinement: có chung dữ liệu không đồng nghĩa được phép dùng xuyên thread

Trên native memory thuộc **Arena.ofConfined()**, phạm vi truy cập bị giới hạn bởi thread sở hữu. Slice không được quyền “thoát” khỏi giới hạn đó.

### Ví dụ runnable: thread khác bị từ chối

**File SliceThreadDemo.java:**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SliceThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment root = arena.allocate(8, 1);
            MemorySegment slice = root.asSlice(2, 3);

            Thread other = new Thread(() -> {
                try {
                    slice.get(ValueLayout.JAVA_BYTE, 0);
                } catch (WrongThreadException expected) {
                    System.out.println("confined slice rejects other thread");
                }
            });

            other.start();
            other.join();

            // Owner thread vẫn truy cập được.
            slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);
            System.out.println("root[2] = "
                    + root.get(ValueLayout.JAVA_BYTE, 2));
        }
    }
}
~~~

Biên dịch/chạy trên JDK 22+:

~~~bash
javac SliceThreadDemo.java
java SliceThreadDemo
~~~

Stdout:

~~~text
confined slice rejects other thread
root[2] = 7
~~~

**WrongThreadException** thuộc **java.lang**, được import ngầm như các class trong java.lang. Nó khác **IndexOutOfBoundsException** và **IllegalStateException**: vấn đề không phải vượt bounds hay arena đã đóng, mà là thread hiện tại không có quyền truy cập segment.

Nếu thực sự cần nhiều thread cùng truy cập native memory, dùng **Arena.ofShared()** và xác định cách phối hợp các thao tác đọc/ghi. **Shared scope cho phép truy cập** nhưng không tự bảo đảm **atomicity, ordering hay absence of data races**.

Ví dụ ý tưởng:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment root = arena.allocate(8, 1);
    MemorySegment slice = root.asSlice(2, 1);

    Thread worker = new Thread(() ->
            slice.set(ValueLayout.JAVA_BYTE, 0, (byte) 12));

    worker.start();
    worker.join();

    System.out.println(root.get(ValueLayout.JAVA_BYTE, 2)); // 12
}
~~~

Đây là **fragment** đặt trong một phương thức cho phép **throws InterruptedException**. **Thread.join()** giúp bảo đảm worker đã hoàn tất trước khi owner đọc kết quả. Trong ứng dụng có nhiều luồng truy cập đồng thời, phải có synchronization thích hợp (lock/VarHandle hoặc primitives phù hợp), không dựa riêng vào việc dùng **asSlice**.

## 10. Alignment: asSlice không biến địa chỉ bất kỳ thành hợp lệ

Slicing có thể tạo địa chỉ bắt đầu không phù hợp một kiểu dữ liệu đa byte. Ví dụ **ValueLayout.JAVA_INT** cần alignment mà layout quy định (thường 4 byte). Dạng **asSlice(offset, size)** chỉ chọn phạm vi byte; việc đọc/ghi **int** với layout có thể thất bại nếu địa chỉ không aligned.

### Fragment minh họa trên native memory được căn 4 byte

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment root = arena.allocate(16, 4);

    // Base + 4 aligned theo 4 byte: hợp lệ.
    MemorySegment aligned = root.asSlice(4, 8, 4);
    aligned.set(ValueLayout.JAVA_INT, 0, 123);

    // Dạng 2 tham số có thể tạo view bắt đầu ở byte 1.
    MemorySegment unaligned = root.asSlice(1, 8);

    // Đọc int tại địa chỉ base+1 vi phạm alignment của JAVA_INT.
    try {
        unaligned.get(ValueLayout.JAVA_INT, 0);
    } catch (IllegalArgumentException expected) {
        System.out.println("misaligned int access rejected");
    }

    // Overload có alignment 4 kiểm tra ngay khi tạo slice.
    try {
        root.asSlice(1, 8, 4);
    } catch (IllegalArgumentException expected) {
        System.out.println("misaligned slice rejected");
    }
}
~~~

Đây là **fragment** hợp lệ khi có import **Arena**, **MemorySegment**, **ValueLayout** và chạy trong phương thức Java; không có **main** độc lập ở đây. Địa chỉ root được arena căn 4, nên root+1 chắc chắn không căn 4. **byteAlignment** không phải tham số để “ép JVM di chuyển” địa chỉ của slice. Nếu vị trí gốc không đạt alignment, API báo lỗi thay vì sao chép dữ liệu vào buffer mới cho đúng alignment.

Với heap segments, độ căn chỉnh phụ thuộc kiểu mảng backing và giới hạn alignment mà runtime có thể bảo đảm. Ví dụ một **byte[]** không nhất thiết hỗ trợ đọc **JAVA_LONG** có alignment 8 ở bất kỳ offset nào. Đừng dùng các cấu trúc đa byte và layout quá chặt trên một heap byte[] mà không xác minh hợp đồng alignment; sử dụng native allocation aligned hoặc layout thích hợp.

**Dạng có MemoryLayout** tiện khi chia record:

~~~java
import java.lang.foreign.MemoryLayout;

MemoryLayout twoInts = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("first"),
        ValueLayout.JAVA_INT.withName("second"));

// root là segment native đủ lớn với offset 8 aligned theo twoInts.
// Tạo view với kích thước và alignment đúng layout.
MemorySegment record = root.asSlice(8, twoInts);
~~~

Đây là **fragment**: **root** được cấp ở nơi khác và phải có kích thước/alignment phù hợp. **asSlice(offset, layout)** không tự deserialize record và không cấp phát object Java chứa các field; nó chỉ tạo view với kích thước/alignment theo layout. Việc đọc field vẫn cần **get**, **VarHandle** hoặc công cụ truy cập phù hợp.

## 11. Read-only: slice kế thừa quyền ghi, không đóng băng backing memory

Khi gọi:

~~~java
MemorySegment readOnlyParent = root.asReadOnly();
MemorySegment child = readOnlyParent.asSlice(2, 4);
~~~

**child.isReadOnly()** trả **true**. Gọi **child.set(...)** sẽ bị từ chối. Tuy nhiên, read-only là **thuộc tính của view**, không phải lệnh biến các byte underlying trở thành bất biến tuyệt đối. Nếu **root** vẫn writable, mã có quyền truy cập **root** có thể tiếp tục sửa vùng nhớ đó; view chỉ đọc sẽ **quan sát** dữ liệu mới khi đọc lại.

Một ví dụ ngắn:

~~~java
byte[] bytes = {1, 2, 3, 4};
MemorySegment root = MemorySegment.ofArray(bytes);
MemorySegment readOnly = root.asReadOnly().asSlice(1, 2);

System.out.println(readOnly.get(ValueLayout.JAVA_BYTE, 0)); // 2
root.set(ValueLayout.JAVA_BYTE, 1, (byte) 9);
System.out.println(readOnly.get(ValueLayout.JAVA_BYTE, 0)); // 9
~~~

Đây là **fragment** cần import **MemorySegment**, **ValueLayout** và đặt trong phương thức Java. Nó minh họa chính xác hai tính chất: **không ghi được qua readOnly**, nhưng **dữ liệu được chia sẻ**.

Nếu ứng dụng cần bảo đảm một bên không thể tác động đến dữ liệu mà bên khác dùng, chỉ cung cấp read-only view **không đủ khi bên kia vẫn giữ writable alias**. Cần kiểm soát tất cả references/permissions, hoặc dùng bản sao độc lập không bị alias.

## 12. asSlice khác copyFrom, MemorySegment.copy và Arrays.copyOfRange

**asSlice**: tạo view, không sao chép dữ liệu, cùng backing memory.

**MemorySegment.copy**, **copyFrom**: thực hiện thao tác **sao chép các byte** từ vùng nguồn sang vùng đích. Vùng đích độc lập hay không phụ thuộc bạn cấp nguồn và đích có alias nhau hay không; để có bản sao **độc lập**, cần một allocation backing memory **khác**.

**Arrays.copyOfRange**: sao chép một phần mảng Java thành mảng Java mới.

Ví dụ runnable trên heap:

### File SliceVsCopyDemo.java

~~~java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public class SliceVsCopyDemo {
    public static void main(String[] args) {
        byte[] source = {5, 10, 15, 20, 25};
        MemorySegment root = MemorySegment.ofArray(source);

        MemorySegment view = root.asSlice(1, 3);
        byte[] independent = Arrays.copyOfRange(source, 1, 4);

        view.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);

        System.out.println("source: " + Arrays.toString(source));
        System.out.println("copy:   " + Arrays.toString(independent));
        System.out.println("view[0]: "
                + view.get(ValueLayout.JAVA_BYTE, 0));

        independent[1] = 77;
        System.out.println("after changing copy: "
                + Arrays.toString(source));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SliceVsCopyDemo.java
java SliceVsCopyDemo
~~~

Stdout:

~~~text
source: [5, 99, 15, 20, 25]
copy:   [10, 15, 20]
view[0]: 99
after changing copy: [5, 99, 15, 20, 25]
~~~

Lý do: **view** alias dữ liệu của **source**, còn **independent** là một mảng mới. Sửa **independent[1]** không làm source thay đổi.

Với native segments, có thể tạo một vùng độc lập rồi copy:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment original = arena.allocate(8, 1);
    original.set(ValueLayout.JAVA_BYTE, 2, (byte) 11);

    MemorySegment view = original.asSlice(2, 3);

    MemorySegment separate = arena.allocate(view.byteSize(), 1);
    separate.copyFrom(view);

    view.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);

    System.out.println(original.get(ValueLayout.JAVA_BYTE, 2)); // 99
    System.out.println(separate.get(ValueLayout.JAVA_BYTE, 0)); // 11
}
~~~

Đây là **fragment** cần các imports FFM. **separate** được allocate trong cùng arena nhưng ở **vùng backing khác**, nên không alias **original**. Việc cùng arena chỉ ảnh hưởng lifecycle, không đồng nghĩa mọi allocation cùng arena chia sẻ byte. Cả hai allocation vẫn bị giải phóng khi arena đóng.

**So sánh chi phí:** một slice thường là tạo metadata/view, tránh copy nội dung; một bản sao độc lập trả chi phí cấp phát và sao chép, nhưng đổi lại giảm aliasing và giúp kiểm soát dữ liệu. Quyết định nên dựa vào ownership, concurrency, lifetime và hiệu năng thực đo; không chọn zero-copy bất chấp tính an toàn.

## 13. asSlice và ByteBuffer: hai view trên cùng byte

API **MemorySegment.asByteBuffer()** có thể tạo **ByteBuffer view** của vùng được segment biểu diễn (phải đáp ứng điều kiện kích thước và trạng thái truy cập của API). ByteBuffer đó cũng **không tự sao chép** dữ liệu. Khi sửa bytes qua buffer, segment nhìn thấy, và ngược lại.

Ý tưởng:

~~~java
import java.nio.ByteBuffer;

MemorySegment root = MemorySegment.ofArray(new byte[] {1, 2, 3, 4});
MemorySegment slice = root.asSlice(1, 2);
ByteBuffer buffer = slice.asByteBuffer();

buffer.put(0, (byte) 99);
System.out.println(root.get(ValueLayout.JAVA_BYTE, 1)); // 99

root.set(ValueLayout.JAVA_BYTE, 2, (byte) 88);
System.out.println(buffer.get(1)); // 88
~~~

Đây là **fragment** cần import **MemorySegment**, **ValueLayout**, **ByteBuffer**; các comment mô tả output khi chạy trong một phương thức Java. Vị trí offset **0** của **buffer** tương ứng offset **0** của **slice**, không phải offset **0** của root.

Với native backing memory của arena, **ByteBuffer view** cũng chịu sự ràng buộc lifetime/thread của backing segment; giữ ByteBuffer sau khi arena đóng không làm bộ nhớ được sống lại. Với read-only MemorySegment, buffer tương ứng cũng phải tuân theo read-only constraints.

Khác biệt: **ByteBuffer** lưu **position**, **limit**, **mark** riêng, có API **slice()** của chính nó. Không nhầm **ByteBuffer.slice()** với **MemorySegment.asSlice()** dù cả hai đều có thể tạo view trên cùng bộ nhớ. Các thao tác absolute **get(index)**/**put(index,value)** giúp ví dụ dễ kiểm tra offset, không bị thay đổi bởi position.

## 14. Dùng slice để chia header và payload của một bản tin

Một ứng dụng thực tế nhận buffer có thể gồm **header 4 byte** rồi một vùng **payload**. Thay vì đưa toàn bộ root vào hàm xử lý payload, ta truyền một slice giới hạn đúng phạm vi.

Ví dụ Java 22+ chạy được trên heap:

### File PacketSlices.java

~~~java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.Arrays;

public class PacketSlices {
    private static void uppercaseAscii(MemorySegment payload) {
        for (long i = 0; i < payload.byteSize(); i++) {
            byte value = payload.get(ValueLayout.JAVA_BYTE, i);
            if (value >= 'a' && value <= 'z') {
                payload.set(ValueLayout.JAVA_BYTE, i,
                        (byte) (value - 'a' + 'A'));
            }
        }
    }

    public static void main(String[] args) {
        byte[] bytes = {1, 0, 0, 3, 'c', 'a', 't'};
        MemorySegment packet = MemorySegment.ofArray(bytes);

        MemorySegment header = packet.asSlice(0, 4);
        MemorySegment payload = packet.asSlice(4);

        System.out.println("header bytes: " + header.byteSize());
        System.out.println("payload bytes: " + payload.byteSize());

        uppercaseAscii(payload);

        System.out.println("packet: " + Arrays.toString(bytes));
        System.out.println("payload text: "
                + (char) payload.get(ValueLayout.JAVA_BYTE, 0)
                + (char) payload.get(ValueLayout.JAVA_BYTE, 1)
                + (char) payload.get(ValueLayout.JAVA_BYTE, 2));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PacketSlices.java
java PacketSlices
~~~

Stdout:

~~~text
header bytes: 4
payload bytes: 3
packet: [1, 0, 0, 3, 67, 65, 84]
payload text: CAT
~~~

Giải thích: bốn byte đầu được để nguyên, ba byte ASCII của payload đổi từ **c a t** sang **C A T**. Mảng gốc đổi tại offsets **4, 5, 6**; không copy dữ liệu sang một mảng khác.

Ví dụ chỉ minh họa chia vùng **đã biết**; nó không tự giải mã header thật, không kiểm tra payload length do nguồn không tin cậy cung cấp và không thay thế protocol parser hoàn chỉnh. Với input thật, phải kiểm tra header size, length field và giới hạn tổng trước khi tạo slice.

Một hàm có thể tạo slice an toàn từ một length do packet cung cấp:

~~~java
static MemorySegment payloadView(
        MemorySegment whole, long headerBytes, long payloadBytes) {
    if (headerBytes < 0 || payloadBytes < 0
            || headerBytes > whole.byteSize()
            || payloadBytes > whole.byteSize() - headerBytes) {
        throw new IllegalArgumentException("invalid packet lengths");
    }
    return whole.asSlice(headerBytes, payloadBytes);
}
~~~

Đây là **fragment** cần import **MemorySegment**. Điều kiện **payloadBytes > whole.byteSize() - headerBytes** tránh phép cộng **headerBytes + payloadBytes** có thể overflow. Slice trả về vẫn alias root; nếu muốn dữ liệu bất biến với bên nhận, hãy cân nhắc tạo copy độc lập.

## 15. Slice độc lập về giới hạn, nhưng không độc lập về ownership

Khi chia MemorySegment cho nhiều hàm hoặc component, nên phân biệt ba trách nhiệm:

**Quyền sở hữu backing memory:** ai cấp phát và ai được đóng arena? Một slice chỉ mượn view; nó không có quyền tự ý đóng tài nguyên hay giữ vô hạn.

**Phạm vi được phép truy cập:** một hàm chỉ xử lý payload nên nhận slice payload; không cần nhận toàn bộ root. Điều này giảm nguy cơ truy cập nhầm header/trailer qua chính view đã được cung cấp.

**Quyền ghi và thời điểm công bố kết quả:** slice writable alias toàn bộ dữ liệu trong khoảng của nó. Nếu code xử lý có thể thất bại sau khi ghi một phần thì backing memory đã có thể đổi; **asSlice không cung cấp rollback**. Có thể dùng read-only view cho code không cần ghi, hoặc copy vào buffer riêng trước khi commit kết quả.

Một thiết kế API thường sáng sủa hơn:

~~~java
// Nhận đúng vùng cần đọc; không biết phần còn lại của root.
static int checksum(MemorySegment payload) {
    int sum = 0;
    for (long i = 0; i < payload.byteSize(); i++) {
        sum += Byte.toUnsignedInt(
                payload.get(ValueLayout.JAVA_BYTE, i));
    }
    return sum;
}
~~~

Đây là **fragment** cần import **MemorySegment**, **ValueLayout**. Kiểu **int sum** có thể overflow với mảng rất dài; nếu checksum nghiệp vụ cần không overflow hoặc cần modulo cụ thể, chọn thuật toán/kiểu dữ liệu thích hợp. Đoạn code chủ yếu minh họa contract nhận view con.

Nhận slice thay vì root không tạo được *sandbox bảo mật hoàn chỉnh*: nếu component còn giữ reference tới root hoặc một alias khác, nó vẫn có thể truy cập vùng rộng hơn. Nhưng API giới hạn đầu vào giúp thiết kế dễ hiểu và kiểm tra hơn.

## 16. Overlapping slices: hai view chồng lấn có thể tác động lẫn nhau

Hai slice **không cần có cùng offset** để chia sẻ một số byte. Ví dụ:

~~~text
root offsets:  0  1  2  3  4  5  6  7  8
slice A:          [1  2  3  4]
slice B:                [3  4  5  6]
overlap:                 3  4
~~~

Nếu **A = root.asSlice(1, 4)** và **B = root.asSlice(3, 4)**, vùng giao nhau là **root offsets 3 và 4**. Sửa **A[2]** tương ứng **root[3]**; **B[0]** nhìn thấy giá trị đó.

Đoạn thử:

~~~java
byte[] data = {0, 1, 2, 3, 4, 5, 6};
MemorySegment root = MemorySegment.ofArray(data);
MemorySegment a = root.asSlice(1, 4);
MemorySegment b = root.asSlice(3, 4);

a.set(ValueLayout.JAVA_BYTE, 2, (byte) 99);

System.out.println(b.get(ValueLayout.JAVA_BYTE, 0)); // 99
~~~

Đây là **fragment** cần imports tương ứng. Nếu nhiều thread ghi lên các overlapping slices, không thể coi chúng là những vùng độc lập. Cần phân chia trách nhiệm theo **byte range**, áp dụng synchronization hoặc cấp phát riêng nếu yêu cầu độc lập. **Non-overlapping** slices trong cùng arena có thể giảm tranh chấp nội dung nhưng vẫn cùng lifecycle và thread-access restrictions.

## 17. Những lỗi hay gặp khi áp dụng asSlice

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tưởng asSlice tạo bản sao mới | Ghi qua slice làm thay đổi root ngoài dự kiến | Dùng allocation/mảng mới và copy dữ liệu nếu cần tách biệt |
| Dùng số phần tử int làm offset | Cắt sai vị trí byte; đọc sai dữ liệu hoặc misaligned | Tính **elementIndex * layout.byteSize()** có kiểm tra overflow |
| Truyền root offset vào **slice.get** | Vượt bounds do slice bắt đầu offset 0 | Tính offset tương đối với slice |
| Tin rằng root còn byte nên slice cũng được đọc | Gây **IndexOutOfBoundsException** | Kiểm tra **slice.byteSize()** và layout width |
| Cho rằng **asSlice(offset,size)** tự xử lý alignment | **get/set** đa byte có thể ném **IllegalArgumentException** | Căn vùng cấp phát và offset; chọn layout đúng |
| Sử dụng slice sau **Arena.close()** | **IllegalStateException** hoặc truy cập bị từ chối | Giữ arena sống suốt thời gian sử dụng view |
| Truyền slice từ confined arena qua thread | **WrongThreadException** | Dùng owner thread hoặc shared arena với synchronization |
| Giữ writable alias khi muốn dữ liệu bất biến | Read-only view vẫn thấy dữ liệu bị sửa từ alias khác | Kiểm soát quyền sở hữu hoặc tạo bản sao |
| Có shared arena nên bỏ qua đồng bộ | Data race, trạng thái quan sát không nhất quán | Thiết kế happens-before/locking/VarHandle phù hợp |
| Xem slice như con trỏ C có thể free | Sai quyền sở hữu native memory | Đóng arena theo contract, không tự free con trỏ của slice |
| Đọc **JAVA_INT** từ một heap byte[] mà không xét alignment | Truy cập có thể bị từ chối | Dùng layout và backing phù hợp |
| Đưa view qua API rồi ngầm đóng arena quá sớm | Bên nhận giữ dangling view | Viết rõ ownership, lifetime và phạm vi API |

## 18. Checklist thiết kế khi truyền slice qua các module

Trước khi giao một MemorySegment slice cho code khác, nên ghi rõ:

1. **Nguồn memory:** heap array, native allocation, memory-mapped file hay direct buffer?
2. **Byte range:** bắt đầu bao nhiêu byte tính từ root, dài bao nhiêu byte, có cho phép zero-length không?
3. **Alignment và layout:** từng field cần căn chỉnh nào? Endianness nào nếu đọc nhiều byte?
4. **Quyền ghi:** readonly view hay writable view? Có alias khác vẫn ghi được không?
5. **Lifetime:** arena nào sở hữu, ai được gọi **close()**, có bảo đảm sống qua callback/asynchronous task không?
6. **Thread access:** confined, shared, heap hay global? Có mechanism đồng bộ tương ứng chưa?
7. **Bản sao hay alias:** caller có chấp nhận việc mutate root không? Muốn snapshot ổn định có cần copy không?
8. **Length validation:** offset/size đến từ dữ liệu không tin cậy có được kiểm tra trước khi tạo view chưa?

Ví dụ hợp đồng có thể được ghi cạnh phương thức:

~~~java
/*
 * payload: view alias với backing memory của caller.
 * Caller phải giữ scope sống trong suốt lời gọi.
 * Hàm chỉ đọc các byte trong [0, payload.byteSize()).
 * Không giữ lại reference sau khi trả về.
 * Không yêu cầu dùng từ thread khác.
 */
static long sumUnsignedBytes(MemorySegment payload) {
    long sum = 0;
    for (long i = 0; i < payload.byteSize(); i++) {
        sum += Byte.toUnsignedInt(
                payload.get(ValueLayout.JAVA_BYTE, i));
    }
    return sum;
}
~~~

Đây là **fragment**; trong ứng dụng thật, cần bổ sung điều kiện dữ liệu quá lớn/overflow nếu kết quả tổng là yếu tố nghiệp vụ. Việc viết rõ contract giúp người gọi không đóng Arena khi một tác vụ bất đồng bộ còn giữ view.

## 19. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Root dài **16 byte**. **root.asSlice(5, 6)** có kích thước và vùng offset nào?

**Đáp án:** **byteSize() = 6**, biểu diễn các byte **root[5]..root[10]**. Offset hợp lệ trong slice là **0..5**.

**Câu 2.** Nếu **root.asSlice(5,6).asSlice(2,3)**, offset **1** trong slice cuối tương ứng root offset mấy?

**Đáp án:** **5 + 2 + 1 = 8**. Mọi offset được cộng theo từng cấp view.

**Câu 3.** Slice có kích thước 4 byte và root có kích thước 100 byte. Có đọc 8 byte bằng **ValueLayout.JAVA_LONG** ở offset 0 của slice không?

**Đáp án:** **Không**. Slice chỉ cho phép 4 byte; truy cập 8 byte vượt bounds của slice dù root còn nhiều dữ liệu.

**Câu 4.** Nếu code ghi **slice.set(JAVA_BYTE,0,7)**, root có thể nhìn thấy giá trị đó không?

**Đáp án:** **Có**, nếu slice/root cùng backing memory, còn sống, writable và có quyền truy cập. Đọc root tại offset tương ứng sẽ nhận giá trị mới theo quy tắc đồng bộ phù hợp.

**Câu 5.** Hai slice được tạo từ cùng một arena nhưng từ **hai lệnh arena.allocate độc lập**, chúng có chắc chắn chia sẻ byte không?

**Đáp án:** **Không**. Chia sẻ arena chỉ có nghĩa cùng phạm vi quản lý lifetime; hai allocation riêng vẫn có các vùng backing riêng.

**Câu 6.** Vì sao giữ **slice** trong một field Java không giúp tránh lỗi sau khi close **Arena.ofConfined()**?

**Đáp án:** Field giữ reference tới view, không kéo dài lifetime của native allocation đã được giải phóng. Access operation sau close bị từ chối.

**Câu 7.** Một read-only slice có tự đảm bảo dữ liệu bên dưới vĩnh viễn không đổi không?

**Đáp án:** **Không**. Nó cấm viết qua view chỉ đọc, không cấm một writable alias khác sửa backing memory.

**Câu 8.** Dùng **asSlice(3, 8, 4)** trên native root có địa chỉ bắt đầu bội số của 4: kết quả?

**Đáp án:** Không thể tạo aligned view tại offset 3 với alignment 4 vì địa chỉ base+3 không aligned; API ném **IllegalArgumentException**.

**Câu 9.** Một native root được tạo bằng **Arena.ofConfined()** rồi truyền slice sang thread khác. Có thể giải quyết bằng việc gọi **asSlice** lần nữa trên thread nhận không?

**Đáp án:** **Không**. Slice kế thừa phạm vi/thread restriction; dùng owner thread hoặc thiết kế **Arena.ofShared()** và synchronization.

**Bài tập A:** Thay **root.asSlice(2,3)** ở ví dụ heap bằng **root.asSlice(2)**. Dự đoán **byteSize()** và các offset hợp lệ; chạy để kiểm chứng. Kết quả mong đợi: **byteSize() == 4**, các offsets **0..3**.

**Bài tập B:** Tạo hai view **root.asSlice(1,3)** và **root.asSlice(2,3)**. Ghi vào view thứ nhất tại offset 1; dự đoán offset tương ứng trong view thứ hai. Kết quả: byte chung tại **root[2]**, tức offset **0** của view thứ hai.

**Bài tập C:** Trong demo native, thay **root.asSlice(4,8)** bằng **root.asSlice(4,12)** trên root 16 byte; kiểm tra đây là slice hợp lệ nhưng truy cập từ offset **12** với **JAVA_INT** vẫn bị từ chối vì ngoài phần đã cấp. Kết quả: **asSlice(4,12)** hợp lệ, **get(JAVA_INT,12)** cần 4 byte ngoài view nên ném **IndexOutOfBoundsException**.

**Bài tập D:** Tạo bản sao độc lập 3 byte của view rồi sửa view. In cả hai để giải thích vì sao bản sao giữ giá trị cũ.

## Tài liệu tham khảo chính thức

- Java SE 22 API — **MemorySegment**, bao gồm **asSlice**, **byteSize**, **scope**, **isReadOnly**, **get/set**: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html
- Java SE 22 API — **Arena** và các scope confined/shared/auto/global: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html
- Java SE 22 API — **ValueLayout** và byte alignment: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html
- Dev.java — **Access Off-Heap or On-Heap Memory with Memory Segments**: https://dev.java/learn/api/io/ffm/access-memory/
- OpenJDK **JEP 454: Foreign Function & Memory API** (finalized in JDK 22): https://openjdk.org/jeps/454

**Ghi nhớ:** **asSlice tạo view, không tạo copy**. Slice và segment gốc cùng backing memory, nên đọc/ghi phản ánh trên cùng các byte. Slice **thu hẹp bounds**, nhưng **không tạo lifetime mới, thread permission mới, quyền ghi mới hoặc bảo đảm đồng bộ mới**. Muốn dữ liệu độc lập, phải cấp backing memory riêng và copy; muốn xử lý native memory an toàn, phải tôn trọng arena, offset, layout và ownership.
