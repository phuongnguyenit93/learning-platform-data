# SegmentAllocator, cấp phát theo layout và chiến lược chia lát vùng nhớ lớn

## Mục tiêu học tập

Trong Foreign Function & Memory API (**FFM**), các đối tượng **MemorySegment** mô tả vùng nhớ; **MemoryLayout** cho biết cấu trúc, kích thước và alignment; **Arena** quyết định phạm vi sống của những vùng nhớ do nó sở hữu. **SegmentAllocator** trừu tượng hóa chiến lược cấp phát. Nó đặc biệt hữu ích khi cần nhiều đối tượng nhỏ, buffer tái sử dụng hoặc chia một vùng nhớ lớn thành những phần có giới hạn truy cập riêng.

Sau bài học, bạn có thể:

1. Phân biệt SegmentAllocator, MemoryLayout, MemorySegment và Arena; giải thích vì sao **Arena extends SegmentAllocator**.
2. Sử dụng **allocate(byteSize, byteAlignment)**, **allocate(MemoryLayout)**, **allocate(elementLayout, count)** và **allocateFrom**.
3. Dùng **SegmentAllocator.slicingAllocator** để lấy những lát liên tiếp trong một slab đã cấp, hiểu alignment padding và lỗi hết dung lượng.
4. Dùng **SegmentAllocator.prefixAllocator** để tái sử dụng một scratch buffer, hiểu rõ vùng nhớ của những lượt cấp phát chồng lên nhau.
5. Dùng **MemorySegment.asSlice** tạo view cho vùng lớn; phân biệt giới hạn truy cập của slice với dung lượng backing memory thực sự.
6. Thiết kế chiến lược **slab, chunking, batching và streaming** với kiểm tra overflow, alignment, ownership, concurrency và arena lifetime.
7. Chạy ví dụ Java 22+ đầy đủ, có stdout xác định; đánh giá lựa chọn cấp phát nào phù hợp với từng workload native.

**Phiên bản:** API **java.lang.foreign** được hoàn thiện trong **JDK 22 (JEP 454)**. Mã Java của bài dùng **JDK 22 trở lên**. Không thể lấy nguyên ví dụ và tuyên bố biên dịch trên Java 17, vì FFM ở những bản trước có API/incubator/preview khác.

## 1. Bốn khái niệm cần tách biệt

| Khái niệm | Câu hỏi nó giải quyết | Giới hạn cần nhớ |
| --- | --- | --- |
| **MemoryLayout** | “Cần bao nhiêu byte, căn chỉnh thế nào, trường nằm ở đâu?” | Layout Java phải được xác nhận với ABI C nếu dùng cho C struct thực |
| **SegmentAllocator** | “Lấy một MemorySegment đủ size/alignment bằng cách nào?” | Không mặc định mỗi lần cấp phát có backing memory riêng |
| **MemorySegment** | “Tôi đang được phép truy cập đoạn byte nào?” | Nó có thể chỉ là **view**, không sở hữu vùng nhớ |
| **Arena** | “Ai cấp phát, và khi nào backing memory hết hiệu lực?” | Arena đóng thì các segment/slice do nó sở hữu không còn truy cập được |

Sơ đồ:

~~~text
   MemoryLayout
      |  byteSize + byteAlignment
      v
   SegmentAllocator.allocate(layout)
      |
      +--- Arena: cấp phát vùng nhớ được quản lý
      |
      +--- slicingAllocator: chia liên tiếp từ slab có sẵn
      |
      +--- prefixAllocator: tái sử dụng phần đầu slab
      |
      v
   MemorySegment
      |  get/set, asSlice, copy
      v
   Native bytes trong scope của arena/backing owner
~~~

Điểm then chốt: **Arena là một loại SegmentAllocator**, nên một API chỉ yêu cầu SegmentAllocator có thể nhận chính Arena. Nhưng SegmentAllocator không bắt buộc là Arena và cũng không bắt buộc gọi malloc cho mỗi lần allocate.

### Giao diện cấp phát tối thiểu

SegmentAllocator là functional interface, có phương thức trừu tượng:

~~~java
MemorySegment allocate(long byteSize, long byteAlignment);
~~~

Hai tham số đều tính bằng **byte**. Alignment là ràng buộc địa chỉ, phải là số dương và lũy thừa của 2 theo API. Allocator trả một MemorySegment tương ứng hoặc báo lỗi theo chính sách của implementation.

Ví dụ ủy quyền về Arena:

~~~java
try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator delegated = (bytes, alignment) ->
            arena.allocate(bytes, alignment);

    MemorySegment value = delegated.allocate(8, 8);
    value.set(ValueLayout.JAVA_LONG, 0, 123L);
}
~~~

Đây là **snippet Java 22+** có thể đặt trong phương thức Java với import **java.lang.foreign.\***. Lambda này chỉ chuyển tiếp yêu cầu tới Arena, không tạo pooling; thông thường có thể sử dụng trực tiếp **arena**.

## 2. Cấp phát theo layout: bớt magic numbers

Phương thức tiện ích:

~~~java
MemorySegment result = allocator.allocate(layout);
~~~

sử dụng **layout.byteSize()** và **layout.byteAlignment()**. Do đó một layout có cấu trúc rõ ràng tốt hơn phép cấp phát dựa trên số byte rải rác trong code.

### 2.1. Một giá trị primitive

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment counter = arena.allocate(ValueLayout.JAVA_INT);
    counter.set(ValueLayout.JAVA_INT, 0, 42);
    System.out.println(counter.get(ValueLayout.JAVA_INT, 0));
}
~~~

Đây là snippet với output **42**; JAVA_INT có size 4 byte. Không nhầm **byteSize** với số lượng phần tử.

### 2.2. Một dãy giá trị

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemoryLayout layout = MemoryLayout.sequenceLayout(
            5, ValueLayout.JAVA_INT
    );
    MemorySegment numbers = arena.allocate(layout);

    for (int index = 0; index < 5; index++) {
        numbers.setAtIndex(ValueLayout.JAVA_INT, index, index + 1);
    }
    System.out.println(numbers.getAtIndex(ValueLayout.JAVA_INT, 4));
}
~~~

Output là **5**. Một sequence 5 int có tổng 20 byte. Có thể sử dụng cách viết ngắn:

~~~java
MemorySegment numbers = arena.allocate(ValueLayout.JAVA_INT, 5);
~~~

Đây là snippet giả định đã có arena còn sống. Overload **allocate(elementLayout, count)** dựng sequence layout từ kích thước mỗi phần tử và count, kiểm tra giá trị âm/tràn phép nhân. Đừng gõ **arena.allocate(5)** rồi tưởng rằng đã cấp đủ **5 số int**: allocate(5) chỉ yêu cầu **5 byte**.

### 2.3. Khởi tạo dữ liệu ngay khi cấp phát

**allocateFrom** giúp cấp và copy dữ liệu ban đầu:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment values =
            arena.allocateFrom(ValueLayout.JAVA_INT, 10, 20, 30);
    System.out.println(
            values.getAtIndex(ValueLayout.JAVA_INT, 1)
    ); // 20

    MemorySegment text = arena.allocateFrom("hello");
    // text chứa một C string UTF-8 có NUL terminator.
}
~~~

**allocateFrom(String)** dùng UTF-8 chuẩn trên JDK 22 và có terminator. Ký tự U+0000 ở giữa vẫn được encode thành byte 00, nên C API đọc bằng strlen có thể xem text bị cắt. Với array primitive, allocateFrom **không tự thêm phần tử terminator của giao thức C**.

Các overload copy dữ liệu có thể phát sinh chi phí chuyển/copy. Việc cấp theo layout không mặc định là zero-copy hay bảo đảm đồng bộ với nguồn ban đầu.

## 3. StructLayout cần padding và alignment tường minh

Giả sử record gồm Java int và Java long, cần long ở byte offset 8:

~~~java
MemoryLayout record = MemoryLayout.structLayout(
    ValueLayout.JAVA_INT.withName("id"),
    MemoryLayout.paddingLayout(4),
    ValueLayout.JAVA_LONG.withName("amount")
);
~~~

Layout này có:

| Thành phần | Offset | Kích thước |
| --- | ---: | ---: |
| **id** | 0 | 4 byte |
| **padding** | 4 | 4 byte |
| **amount** | 8 | 8 byte |
| **Tổng** |  | **16 byte** |

Natural byte alignment của layout là 8 theo JAVA_LONG. Có thể tìm offset bằng path:

~~~java
long amountOffset = record.byteOffset(
        MemoryLayout.PathElement.groupElement("amount")
);
~~~

Không nên lặp magic number **8** tại nhiều chỗ nếu field offset đã được biểu diễn bằng MemoryLayout. **MemoryLayout.structLayout không tự chèn padding theo ABI C.** Khi mô tả C struct, cần đối chiếu **sizeof, _Alignof, offsetof**, compiler flags và data model của native library thực tế.

**Lưu ý quan trọng:** Trong bài demo, layout được định nghĩa theo các ValueLayout của Java, nên kết quả size/offset cố định. Điều đó **không chứng minh** mọi C struct có int và long đều giống vậy. Chẳng hạn C long trên Windows x64 thường 32 bit, khác Java long 64 bit.

## 4. Chiến lược 1: slicingAllocator chia các lát liên tiếp

Factory trong JDK 22:

~~~java
SegmentAllocator allocator =
        SegmentAllocator.slicingAllocator(slab);
~~~

Với **slab** là MemorySegment đã được cấp từ một Arena, allocator trả các slice liên tiếp. Mỗi allocation có thể thêm khoảng padding nhỏ để bảo đảm alignment.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment slab = arena.allocate(64, 8);
    SegmentAllocator bump =
            SegmentAllocator.slicingAllocator(slab);

    MemorySegment a = bump.allocate(ValueLayout.JAVA_LONG);
    MemorySegment b = bump.allocate(ValueLayout.JAVA_LONG);

    a.set(ValueLayout.JAVA_LONG, 0, 11L);
    b.set(ValueLayout.JAVA_LONG, 0, 22L);
}
~~~

Trong ví dụ, slab bắt đầu ở địa chỉ aligned 8. Hai lần cấp phát đều 8 byte aligned 8, nên **a** chiếm offset 0–7, **b** chiếm offset 8–15. Chúng không chồng lấn nếu chỉ xét những allocation do **bump** trả ra.

### 4.1. Mô hình bump allocator

~~~text
Slab: 64 byte, base aligned 8
+-------------+-------------+-------------------------+
|   a: 8 B    |   b: 8 B    |    chưa phân phối      |
+-------------+-------------+-------------------------+
offset 0      8            16                       64
                                  ^
                   cursor di chuyển tới sau b
~~~

**Mỗi allocation thành công:** allocator tìm vị trí đáp ứng alignment rồi trả một view. **Không tự cấp thêm slab**, không có cơ chế free riêng cho từng view; vòng đời của tất cả vẫn theo slab/arena gốc.

### 4.2. Padding có thể tiêu thụ dung lượng

Ví dụ cấp trước 1 byte rồi cấp long 8 byte có thể có sơ đồ:

~~~text
offset:  0 1 2 3 4 5 6 7 | 8 9 10 11 12 13 14 15
         [a] [ padding ] | [       b: 8 B        ]
~~~

Tổng dữ liệu logic chỉ là 1 + 8 = 9 byte, nhưng cursor đã đi tới offset 16. Vì vậy **không luôn đúng** khi lấy tổng layout.byteSize của từng request làm capacity slab tối thiểu. Với các layout hỗn hợp, còn phải dự trù alignment padding.

Nếu dùng một layout có stride phù hợp và base aligned đúng mức, có thể tránh nhiều khoảng lãng phí; nhưng vẫn phải kiểm tra yêu cầu ABI của dữ liệu thật.

### 4.3. Khi slab hết chỗ

~~~java
try (Arena arena = Arena.ofConfined()) {
    SegmentAllocator bump =
            SegmentAllocator.slicingAllocator(
                    arena.allocate(16, 8)
            );

    bump.allocate(ValueLayout.JAVA_LONG);
    bump.allocate(ValueLayout.JAVA_LONG);

    try {
        bump.allocate(ValueLayout.JAVA_LONG);
    } catch (IndexOutOfBoundsException expected) {
        System.out.println("slab full");
    }
}
~~~

Đây là snippet minh họa. Lần thứ ba muốn thêm 8 byte, trong khi slab 16 byte đã được dùng hết, nên **slicingAllocator** ném **IndexOutOfBoundsException**.

Không nên mặc định có thể retry trên **cùng allocator** và nó sẽ tự mở rộng. Cần tạo slab/allocator mới hoặc lựa chọn lỗi/quota. Khi có thể ước lượng số record, tính capacity trước thường đơn giản và hiệu quả hơn việc dùng exception như một vòng điều phối thường xuyên.

### 4.4. Thread safety của slicingAllocator

Theo tài liệu JDK 22, **slicingAllocator không thread-safe**. Kể cả slab xuất phát từ **Arena.ofShared()**, điều đó không tự biến cursor của allocator thành concurrent-safe. Hai thread cấp qua cùng một allocator mà không được đồng bộ có thể cạnh tranh state nội bộ.

Các cách thiết kế tốt hơn:

- Mỗi worker sở hữu slab và slicingAllocator của riêng mình.
- Một thread cấp những slice không overlap rồi chuyển chúng cho worker khi scope cho phép.
- Dùng allocator custom với cơ chế synchronization/atomic reservation được kiểm thử nếu thật sự cần.
- Nếu chỉ cần cấp phát từ arena chung, có thể dùng trực tiếp Arena phù hợp mà không tự thêm một cursor dùng chung.

## 5. Chiến lược 2: prefixAllocator tái sử dụng buffer

Factory:

~~~java
SegmentAllocator reusable =
        SegmentAllocator.prefixAllocator(scratch);
~~~

Khác với slicingAllocator, **prefixAllocator** trả slice bắt đầu từ **offset 0 của cùng segment** cho mỗi lần gọi, miễn kích thước/alignment phù hợp.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment scratch = arena.allocate(32, 8);
    SegmentAllocator reused =
            SegmentAllocator.prefixAllocator(scratch);

    MemorySegment a = reused.allocate(ValueLayout.JAVA_INT);
    a.set(ValueLayout.JAVA_INT, 0, 10);

    MemorySegment b = reused.allocate(ValueLayout.JAVA_INT);
    b.set(ValueLayout.JAVA_INT, 0, 20);

    System.out.println(a.get(ValueLayout.JAVA_INT, 0));
}
~~~

Output là **20**, không phải 10. Hai view cùng trỏ vào phần đầu của scratch. Đây là **overlap cố ý**.

### Khi nào việc tái sử dụng là hợp lệ?

- Một parser cần vùng nhớ tạm để xử lý **một request tại một thời điểm**.
- Một downcall muốn chỗ ghi kết quả nhỏ và **kết quả lần trước đã dùng xong** trước khi cấp chỗ cho lần tiếp theo.
- Một vòng lặp streaming muốn tái sử dụng buffer, **không giữ reference/pointer sang lần sau**.

Không sử dụng prefixAllocator khi cần giữ nhiều kết quả đồng thời. Đặc biệt nguy hiểm khi C API giữ pointer bất đồng bộ: lần ghi tiếp theo có thể thay đổi dữ liệu mà native worker vẫn đang đọc.

**Điểm dễ nhầm:** Tài liệu JDK 22 nói bản thân **prefixAllocator thread-safe**, nhưng các memory segments nó cấp **có thể chồng lấn**. Nhiều thread ghi vào cùng prefix vẫn có data race; tính thread-safe của allocator **không làm dữ liệu bên trong tự đồng bộ**.

### So sánh hai factory

| Tiêu chí | slicingAllocator | prefixAllocator |
| --- | --- | --- |
| Vị trí cấp phát | Các slice liên tiếp, cursor tiến lên | Slice luôn bắt đầu từ prefix offset 0 |
| Kết quả cấp sau có ghi chồng kết quả trước không? | Không giữa các slice được allocator cấp thành công | **Có thể, theo thiết kế** |
| Tự tăng dung lượng slab? | Không | Không |
| Hết capacity | Ném **IndexOutOfBoundsException** | Ném **IndexOutOfBoundsException** nếu request không vừa |
| Thread safety của allocator | **Không thread-safe** | Bản thân allocator có thể được gọi đồng thời; data overlap vẫn không an toàn |
| Phù hợp | Nhiều record cùng tồn tại trong batch | Scratch tạm được dùng tuần tự |

Không nên dùng tên “allocator” rồi suy ra tất cả kết quả đều độc lập như các lần malloc khác nhau.

## 6. MemorySegment.asSlice: cắt view không cấp thêm bộ nhớ

Ngoài hai factory, có thể chọn byte offset thủ công:

~~~java
MemorySegment child = parent.asSlice(startByte, lengthByte);
~~~

Hoặc cắt đúng kích thước/alignment của một layout:

~~~java
MemorySegment record = parent.asSlice(startByte, recordLayout);
~~~

Các tính chất:

1. **View cùng backing memory**: đọc/ghi qua child thấy dữ liệu của parent tại cùng byte offset, và ngược lại.
2. **Spatial bounds hẹp hơn**: byteSize của child chỉ bằng length/layout, nên truy cập ngoài slice bị từ chối ngay cả khi parent còn chỗ.
3. **Temporal scope không tách rời**: child chịu lifetime của parent/arena; đóng arena làm cả hai không hợp lệ.
4. **Thread accessibility giữ theo scope**: slice từ confined arena không thể tự trở thành shared chỉ bằng asSlice.
5. **asSlice(offset, layout)** kiểm tra alignment của vị trí cắt theo layout.

Ví dụ:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment parent = arena.allocate(1_024, 8);
    MemorySegment child = parent.asSlice(128, 64);

    child.set(ValueLayout.JAVA_INT, 0, 777);
    System.out.println(parent.get(ValueLayout.JAVA_INT, 128));
}
~~~

Output **777**. Sau khi đóng arena, cả parent lẫn child không được truy cập nữa. Java giữ reference tới child **không có nghĩa** native backing memory của parent sống lại.

### Slice khác copy

- **asSlice**: tạo view khác trên **cùng byte region**.
- **MemorySegment.copy** hoặc **copyFrom**: chuyển nội dung từ segment nguồn sang một vùng đích đã có, tùy overload.
- **arena.allocate**: yêu cầu vùng nhớ mới do arena quản lý.
- **SegmentAllocator.slicingAllocator**: phân phối các view trong một slab gốc.

Nếu yêu cầu **bản sao độc lập** để xử lý đồng thời không ghi đè, cần cấp backing riêng và copy; chỉ asSlice không tạo độc lập.

## 7. Chia lát vùng nhớ lớn: hai loại “tiết kiệm” khác nhau

Một vùng 1 GiB có thể được chia thành những view 64 KiB bằng asSlice. Điều đó giúp **code mỗi lượt chỉ nhìn thấy 64 KiB** và giảm nguy cơ đọc vượt phạm vi chunk.

Tuy nhiên, **nếu bạn đã cấp 1 GiB, tổng native allocation vẫn là 1 GiB**. Chia view không thu hồi 1 GiB thành 64 KiB.

~~~text
Backing region đã cấp: 1 GiB
+--------+--------+--------+----------- ... --------+
| chunk0 | chunk1 | chunk2 |                      |
+--------+--------+--------+----------- ... --------+
  view     view     view

Không có copy hoặc malloc riêng cho từng view.
Backing region sống cho tới khi owner đóng/giải phóng.
~~~

Phân biệt rõ:

| Chiến lược | Backing memory | Thế mạnh | Chi phí/giới hạn |
| --- | --- | --- | --- |
| Một slab lớn + **asSlice** | Bằng kích thước cả slab | Offset rõ, bounds từng phần, không copy | Peak memory vẫn bằng slab |
| Slab + **slicingAllocator** | Bằng kích thước slab | Nhiều object nhỏ cùng lifetime, cấp nhanh | Cursor/capacity, không free per slice |
| Một scratch + **prefixAllocator** | Gần kích thước scratch | Reuse, ít allocation mới | Không giữ đồng thời nhiều kết quả |
| **Batch arenas** | Tổng các batch đang in flight | Có thể đóng giải phóng từng batch | Cần orchestration và backpressure |
| **Streaming/mapped window** | Chỉ những cửa sổ đang dùng | Giới hạn working memory | I/O, partial reads, lifecycle phức tạp hơn |

### Vòng lặp chunk đúng kiểu long

~~~java
long offset = 0;
while (offset < big.byteSize()) {
    long remaining = big.byteSize() - offset;
    long take = Math.min(chunkBytes, remaining);

    MemorySegment chunk = big.asSlice(offset, take);
    // Xử lý chunk trong phạm vi byteSize của nó.

    offset += take;
}
~~~

Đây là snippet, yêu cầu **big** hợp lệ và **chunkBytes > 0**. Dùng **long** vì kích thước segment có thể vượt **Integer.MAX_VALUE**. Việc dùng **remaining = total - offset** trước khi tính take giúp tránh lỗi arithmetic kiểu **offset + chunkBytes** vượt long.

Nếu **chunk** cần chứa các phần tử int, hãy bảo đảm take và offset phù hợp alignment/stride. Nếu phần tử có thể nằm giữa hai chunk, cần duy trì phần dư hoặc thay đổi chunk boundary theo record size.

### Streaming thực sự

Với file lớn hơn nhiều so với native RAM budget, cấp **một buffer 64 KiB**, nạp một phần, xử lý và **chỉ reuse sau khi mọi consumer xong**. Như vậy memory tạm có thể gần **O(chunkSize)**, không cần cấp trước toàn bộ file.

Nếu nhiều batch xử lý song song, peak memory gần **số batch đang chạy × dung lượng batch**, cộng runtime overhead. Phải giới hạn số batch **in flight** để không mất khả năng kiểm soát RSS.

## 8. Tính dung lượng: size, alignment và overflow

### 8.1. Layout size và số record

Với N record cùng layout, logical bytes là:

\[
B = N \times \mathrm{recordLayout.byteSize()}
\]

Trong code hãy tránh tràn:

~~~java
long bytes = Math.multiplyExact(
        count,
        recordLayout.byteSize()
);
~~~

Snippet này giả định count và recordLayout đã được khai báo. **Math.multiplyExact** ném **ArithmeticException** nếu phép nhân vượt phạm vi long. Sau đó vẫn cần kiểm tra **bytes ≤ quota của ứng dụng**; một giá trị vừa long vẫn có thể vượt RAM/swap/giới hạn container.

### 8.2. Alignment padding

Một allocator dựa trên slab có thể phải đẩy cursor tới một địa chỉ aligned theo yêu cầu request. Với base đã căn 8:

~~~text
1 byte dữ liệu + 7 byte padding + 8 byte dữ liệu
= 16 byte được tiêu thụ để lưu 9 byte hữu ích
~~~

Do vậy slab capacity có thể phải lớn hơn tổng layout.byteSize các request nếu có kích thước/alignment hỗn hợp. Thực tế còn phụ thuộc thứ tự allocation, alignment của base address và chính sách allocator.

**Không dùng công thức tự tính alignedOffset không kiểm tra overflow.** Alignment là số lũy thừa 2, nhưng phép cộng offset + align - 1 vẫn có thể tràn long. Khi có thể, dùng các phương thức chính thức của FFM với layout đã kiểm tra, và quản lý quota trước khi cấp phát.

### 8.3. Allocation exhaustion

- **slicingAllocator**: hết chỗ → **IndexOutOfBoundsException**, cần slab mới hoặc báo lỗi.
- **Arena**: có thể không cấp phát thành công do áp lực memory hoặc yêu cầu không hợp lệ; không nên biến failure thành vòng retry vô hạn.
- **prefixAllocator**: request lớn hơn prefix có thể dùng → **IndexOutOfBoundsException**.
- **asSlice**: offset/length ngoài parent → **IndexOutOfBoundsException**.

Một error handler không nên catch rộng mọi Throwable rồi trả “empty buffer”: điều đó có thể che lỗi cấp phát và khiến C API ghi vượt vùng nhớ thật.

## 9. Ví dụ Java 22+ hoàn chỉnh

Ví dụ không cần native C library. Nó chứng minh **allocate(MemoryLayout)**, layout padding, slicingAllocator, prefixAllocator và asSlice trên vùng 1 MiB.

Tạo file **AllocatorSlicingDemo.java**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SegmentAllocator;
import java.lang.foreign.ValueLayout;

public final class AllocatorSlicingDemo {
    private static final MemoryLayout ENTRY =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("id"),
                    MemoryLayout.paddingLayout(4),
                    ValueLayout.JAVA_LONG.withName("amount")
            );

    private static final long AMOUNT_OFFSET =
            ENTRY.byteOffset(
                    MemoryLayout.PathElement.groupElement("amount")
            );

    private AllocatorSlicingDemo() {
    }

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            // Slab chứa nhiều allocation nhỏ.
            MemorySegment slab = arena.allocate(
                    256, ENTRY.byteAlignment()
            );
            SegmentAllocator bump =
                    SegmentAllocator.slicingAllocator(slab);

            // Hai record cùng tồn tại, mỗi record 16 byte.
            MemorySegment first = bump.allocate(ENTRY);
            MemorySegment second = bump.allocate(ENTRY);

            first.set(ValueLayout.JAVA_INT, 0, 7);
            first.set(ValueLayout.JAVA_LONG, AMOUNT_OFFSET, 70L);
            second.set(ValueLayout.JAVA_INT, 0, 8);
            second.set(ValueLayout.JAVA_LONG, AMOUNT_OFFSET, 80L);

            // Mảng 4 số int: 4 * 4 = 16 byte.
            MemoryLayout fourInts =
                    MemoryLayout.sequenceLayout(
                            4, ValueLayout.JAVA_INT
                    );
            MemorySegment numbers = bump.allocate(fourInts);

            int sum = 0;
            for (int i = 0; i < 4; i++) {
                numbers.setAtIndex(ValueLayout.JAVA_INT, i, i + 1);
                sum += numbers.getAtIndex(ValueLayout.JAVA_INT, i);
            }

            // Scratch riêng ở byte offset 128: tránh vùng
            // đã dùng cho 2 record và mảng phía trước.
            MemorySegment scratch = slab.asSlice(128, 32);
            SegmentAllocator reusable =
                    SegmentAllocator.prefixAllocator(scratch);

            MemorySegment oldView =
                    reusable.allocate(ValueLayout.JAVA_INT);
            oldView.set(ValueLayout.JAVA_INT, 0, 111);

            MemorySegment newView =
                    reusable.allocate(ValueLayout.JAVA_INT);
            newView.set(ValueLayout.JAVA_INT, 0, 222);

            boolean reused =
                    oldView.get(ValueLayout.JAVA_INT, 0) == 222;

            // 1 MiB được chia thành 16 view, mỗi view 64 KiB.
            MemorySegment large = arena.allocate(
                    1_048_576L,
                    ValueLayout.JAVA_INT.byteAlignment()
            );

            final long chunkSize = 65_536L;
            long offset = 0;
            long chunkCount = 0;
            long markerSum = 0;

            while (offset < large.byteSize()) {
                long remaining = large.byteSize() - offset;
                long take = Math.min(chunkSize, remaining);
                MemorySegment slice = large.asSlice(offset, take);

                int marker = (int) ++chunkCount;
                slice.set(ValueLayout.JAVA_INT, 0, marker);
                markerSum += slice.get(ValueLayout.JAVA_INT, 0);

                offset += take;
            }

            System.out.println("layoutBytes=" + ENTRY.byteSize());
            System.out.println("amountOffset=" + AMOUNT_OFFSET);
            System.out.println(
                    "first=" + first.get(ValueLayout.JAVA_INT, 0)
                    + ":" + first.get(
                            ValueLayout.JAVA_LONG, AMOUNT_OFFSET
                    )
            );
            System.out.println(
                    "second=" + second.get(ValueLayout.JAVA_INT, 0)
                    + ":" + second.get(
                            ValueLayout.JAVA_LONG, AMOUNT_OFFSET
                    )
            );
            System.out.println("arraySum=" + sum);
            System.out.println("prefixReused=" + reused);
            System.out.println("chunks=" + chunkCount);
            System.out.println("chunkMarkerSum=" + markerSum);
        }
    }
}
~~~

### Biên dịch và chạy

Cần cài **JDK 22+**. Không dùng javac của JDK 17 cho class trên:

~~~bash
javac AllocatorSlicingDemo.java
java AllocatorSlicingDemo
~~~

Các thao tác demo chỉ dùng FFM memory allocation/access; không có Linker.downcall hoặc native symbol loading, nên **không cần --enable-native-access** cho riêng ví dụ này trên JDK 22.

**Stdout chính xác khi chạy thành công:**

~~~text
layoutBytes=16
amountOffset=8
first=7:70
second=8:80
arraySum=10
prefixReused=true
chunks=16
chunkMarkerSum=136
~~~

### Phân tích kết quả

- **layoutBytes=16**: 4 byte int, 4 byte padding, 8 byte long.
- **amountOffset=8**: được lấy bằng layout path; không hardcode offset khi đọc/ghi amount.
- **first=7:70**, **second=8:80**: slicingAllocator cấp hai view không chồng lấn của slab.
- **arraySum=10**: dãy 1,2,3,4 được lưu trong sequence layout và cộng bằng getAtIndex.
- **prefixReused=true**: oldView và newView cùng trỏ vào prefix; ghi 222 qua view mới cũng làm view cũ đọc ra 222. Đây là **hành vi mong muốn của prefixAllocator**, nhưng không phù hợp nếu dữ liệu cũ còn cần sử dụng.
- **chunks=16**: 1.048.576 / 65.536 = 16 view.
- **chunkMarkerSum=136**: 1 + 2 + ... + 16 = 136, lấy từ offset 0 của từng view.
- **Arena.close** sau khối try làm tất cả segment thuộc arena không thể truy cập hợp lệ nữa; không có phép free riêng cho các slice.

### Giới hạn của demo

Đây là một bài **FFM allocation Java thuần**, không chứng minh ABI của C struct thật, không có file streaming, không sử dụng đa luồng và không cho native C giữ pointer. Giá trị output được suy ra từ source và hợp đồng API; để xác minh triển khai trên máy của bạn, vẫn cần chạy bằng JDK 22+ thực tế.

Một phần quan trọng: đoạn chia 1 MiB **vẫn chiếm 1 MiB backing memory**. Nó chứng minh kỹ thuật làm việc từng view, chứ không chứng minh tiết kiệm peak RAM của một pipeline streaming.

## 10. Vòng đời Arena và khả năng truy cập từ thread

### 10.1. Arena.ofConfined()

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(256);
    MemorySegment view = block.asSlice(0, 32);
    view.set(ValueLayout.JAVA_INT, 0, 9);
}
~~~

Confined arena cho phép truy cập trên **thread sở hữu scope** và giải phóng có kiểm soát khi đóng. Đây là lựa chọn phù hợp cho allocation theo request/batch trên một thread.

### 10.2. Arena.ofShared()

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment block = arena.allocate(256);
    // Các worker có thể truy cập theo quy tắc shared arena,
    // nhưng vẫn phải đồng bộ hóa dữ liệu và đóng scope đúng lúc.
}
~~~

Shared arena cho phép sử dụng từ nhiều thread; **không làm Java/C data race tự biến mất**. Các slice giao cho nhiều thread nên không overlap nếu xử lý độc lập, và arena chỉ được đóng khi consumer cuối đã hoàn tất.

**Cực kỳ quan trọng:** Shared arena **không làm slicingAllocator trở thành thread-safe**; theo JDK 22, allocator này có cursor không an toàn nếu nhiều thread đồng thời allocate.

### 10.3. Arena.ofAuto() và Arena.global()

- **Arena.ofAuto()** có quản lý lifetime tự động; thời điểm native memory thực sự được thu hồi không xác định.
- **Arena.global()** tồn tại dài theo vòng đời VM, không dùng try-with-resources để đóng.

Với dữ liệu native lớn cần giải phóng rõ ràng theo batch, Arena.ofConfined/ofShared với close có kiểm soát thường giúp dự đoán peak memory dễ hơn.

### 10.4. Slice kế thừa scope của owner

Giữ MemorySegment slice trong một List Java không khiến backing memory sống độc lập. Nếu arena sở hữu parent đã đóng, mọi view liên quan mất hiệu lực. **Không có free(slice)** trong FFM; muốn giải phóng sớm một phần của dữ liệu, hãy cấp part đó trong một arena/batch có lifetime riêng ngay từ đầu.

## 11. Chiến lược slab, batch và streaming trong thực tế

### A. Nhiều record nhỏ sống cùng một batch

- Cấp một slab bằng Arena theo ngân sách.
- Sử dụng slicingAllocator để tạo các record theo layout.
- Không đóng arena khi bất kỳ record nào còn được dùng.
- Đóng cả arena khi toàn batch kết thúc.

Ưu điểm là locality và giảm số thao tác cấp phát nhỏ. Nhược điểm là **không giải phóng được một record riêng**, cần biết quota và dự phòng padding.

### B. Buffer tạm cho tác vụ nối tiếp

- Cấp một scratch buffer nhỏ.
- Dùng prefixAllocator hoặc asSlice để lấy view phù hợp.
- Xử lý xong, sau đó mới ghi đè phần cũ cho task tiếp theo.

Ưu điểm là reuse mà không tăng memory theo số request. Nhược điểm là **không được chia sẻ kết quả cũ trong khi buffer bị tái sử dụng**.

### C. Vùng đã có rất lớn, cần xử lý từng khối

- Lấy tổng **byteSize** thật.
- Xác định chunkSize dương và phù hợp độ căn chỉnh.
- Lặp offset kiểu long; dùng **remaining = total - offset** và asSlice.
- Chỉ làm việc trong bounds của slice.
- Không giả định việc tạo slice giảm allocation của parent.

Có thể chia phần việc cho worker bằng những slice không overlap thuộc shared arena, nhưng phải quản synchronization, lifetime và chính sách lỗi.

### D. Dữ liệu lớn hơn RAM budget

Không cấp nguyên một file 200 GiB chỉ để tạo các view 64 KiB. Thay vào đó dùng streaming, mapped windows hoặc nhiều batch có giới hạn số lượng đang chạy. Cách này có thể giữ native working memory gần **O(chunkSize × số buffer đang in flight)**.

Một batch chỉ được giải phóng khi không còn worker, callback hoặc native library dùng pointer của nó.

### E. C API giữ pointer sau khi trả về

Nếu native C lưu địa chỉ MemorySegment để sử dụng bất đồng bộ, **không đóng arena hoặc tái sử dụng prefix** ngay khi downcall kết thúc. FunctionDescriptor và SegmentAllocator không tự suy luận hợp đồng này; cần một API unregister/drain hoặc cơ chế chuyển quyền sở hữu rõ ràng.

## 12. Lưu ý về ABI, C pointer và deallocator

Nếu memory cấp bằng Java Arena, Arena chịu trách nhiệm giải phóng theo scope. Nếu C API **tự cấp phát và trả con trỏ**, không mặc định Arena.close có thể giải phóng địa chỉ đó. Cần biết deallocator do thư viện cung cấp (free, release, destroy hoặc allocator riêng).

Tương tự, **MemoryLayout.structLayout** của Java không chứng minh tương thích với C struct đã compile. Khi muốn truyền struct pointer sang C, hãy xác minh:

- **sizeof**, **_Alignof**, **offsetof** các field cần dùng.
- Kiểu C có độ rộng phụ thuộc ABI như **long** và **size_t**.
- Endianness nếu dữ liệu là format nhị phân/ABI có yêu cầu riêng.
- Pointer có thể null không; độ dài tính theo byte hay phần tử.
- Native function chỉ mượn pointer trong lời gọi hay lưu để dùng sau.
- Ai đóng arena, ai chịu trách nhiệm unregister callback và cleanup.

FFM kiểm tra bounds/lifetime khi code Java truy cập MemorySegment, nhưng **không thể bảo vệ khỏi mọi lỗi C native code** sau khi đã đưa raw pointer cho C. Một C function nhận pointer và capacity sai vẫn có thể ghi vượt vùng thật hoặc giữ dangling pointer.

## 13. Lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi mọi allocate đều là một malloc độc lập | Ownership/free sai | Phân biệt arena-owned memory với slice từ slab |
| Truyền số phần tử như byteSize | Cấp thiếu byte | Dùng allocate(elementLayout,count) |
| Quên alignment padding trong slab | Hết chỗ sớm | Tính capacity có padding, kiểm tra quota |
| Nghĩ structLayout tự thêm C padding | Layout sai hoặc tạo layout lỗi | Padding tường minh và đối chiếu ABI |
| Chia sẻ slicingAllocator cho nhiều threads | Race cursor | Mỗi thread riêng hoặc đồng bộ hóa |
| Dùng prefixAllocator giữ nhiều kết quả | Lần sau ghi đè lần trước | Dùng slicingAllocator/arena khi cần non-overlap |
| Prefix thread-safe nên data cũng thread-safe | Data race | Bảo vệ dữ liệu hoặc per-thread scratch |
| Nghĩ asSlice cấp vùng nhớ mới | Đánh giá sai RSS | Ghi nhận backing region vẫn còn nguyên |
| Đóng arena khi native worker dùng pointer | Use-after-free | Đợi worker/drain trước khi close |
| Dùng offset int cho vùng >2 GiB | Overflow | Dùng long, Math.multiplyExact |
| Dùng get/set tại offset lệch alignment | Access exception | Chọn layout/offset/alignment hợp lệ |
| Dùng unaligned layout để che C ABI sai | Native function vẫn có thể vi phạm contract | Xác minh ABI, chỉ dùng unaligned khi format cho phép |
| Cho C giữ pointer tới prefix scratch qua request | Đọc dữ liệu đã bị overwrite | Buffer có ownership riêng hoặc quy trình completion |
| Một slab khổng lồ cho dữ liệu streaming | Peak native RSS cao | Chunk/batch/reuse với backpressure |
| Bỏ qua allocation exhaustion | Ghi sai hoặc không phục hồi đúng | Giới hạn capacity và xử lý lỗi rõ |

## 14. Checklist trước khi đưa vào production

- [ ] Dùng **JDK 22+** nếu dựa trên FFM ổn định như các API trong ví dụ.
- [ ] Có **layout** đúng byteSize, byteAlignment, padding và ABI thực nếu tương tác C.
- [ ] Chọn **Arena** theo owner và thời điểm giải phóng, không để slice thoát scope không hợp lệ.
- [ ] Cấp theo layout/count thay vì nhầm số phần tử với số byte.
- [ ] Với slicingAllocator, dự trù alignment padding và xử lý hết dung lượng.
- [ ] Không chia sẻ slicingAllocator không thread-safe một cách tự do.
- [ ] Với prefixAllocator, đảm bảo dữ liệu trước không còn dùng khi reuse.
- [ ] Với asSlice, biết rõ view dùng chung memory/scope với parent.
- [ ] Dùng **long offsets**, phép toán chống overflow và giới hạn quota native bytes.
- [ ] Nếu data lớn, phân biệt **cắt view trên backing lớn** với **streaming giảm peak memory**.
- [ ] Nếu đa luồng, chọn shared/confined arena đúng và có synchronization.
- [ ] Nếu có C API, xác nhận ownership, pointer retention, length và deallocator.
- [ ] Kiểm thử bounds, misalignment, allocation exhaustion, arena close, race và native crash.
- [ ] Benchmark slab size, allocation rate, copy cost, RSS và latency trên workload thật.

## 15. Câu hỏi tự kiểm tra

**1. Arena và SegmentAllocator có phải hai tên của cùng một đối tượng?**

**Trả lời:** Không. Arena **kế thừa SegmentAllocator** và quản lifetime của allocations. Nhưng một SegmentAllocator có thể chỉ trả slices của một slab do Arena khác sở hữu.

**2. allocate(MemoryLayout) sử dụng những thông tin nào?**

**Trả lời:** Dùng **layout.byteSize()** và **layout.byteAlignment()** để gửi yêu cầu cấp phát. Layout có thể là primitive, sequence hoặc struct.

**3. slicingAllocator có tự cấp thêm slab khi hết chỗ không?**

**Trả lời:** Không. Nó ném **IndexOutOfBoundsException** nếu không tìm được slice phù hợp với size/alignment trong backing segment đã cho.

**4. prefixAllocator trả kết quả thứ hai thì kết quả thứ nhất có còn độc lập không?**

**Trả lời:** Không. Nó tái sử dụng prefix; hai view có thể cùng trỏ tới bytes giống nhau và bị ghi đè.

**5. Chia một MemorySegment 1 GiB thành views 64 KiB có giảm native allocation xuống 64 KiB không?**

**Trả lời:** Không. Slicing chỉ giới hạn phạm vi truy cập của từng view; backing memory vẫn là 1 GiB.

**6. Arena.ofShared có làm slicingAllocator thread-safe không?**

**Trả lời:** Không. Shared arena cho phép các thread truy cập memory theo scope, nhưng cursor của slicingAllocator riêng vẫn không thread-safe.

**7. Vì sao phải dùng Math.multiplyExact cho count × recordSize?**

**Trả lời:** Tránh overflow của long khiến cấp phát sai dung lượng. Sau đó vẫn cần giới hạn quota và xử lý memory pressure.

**8. Khi nào prefixAllocator là lựa chọn phù hợp?**

**Trả lời:** Khi cần scratch buffer tái sử dụng **tuần tự**, dữ liệu trước không còn được dùng và không có native callback/worker giữ pointer.

**9. Có thể tự free một slice của slab trước khi Arena đóng không?**

**Trả lời:** Không như một allocation độc lập. Slice là view dùng chung backing/lifetime; muốn giải phóng từng batch cần chia ownership/arena ngay từ thiết kế.

**10. Một C library giữ pointer sau khi downcall trả về thì có thể đóng Arena ngay không?**

**Trả lời:** Không. Vùng nhớ phải còn sống tới khi C không còn dùng pointer, có thể cần unregister/drain workers/callbacks trước khi close.

## Tài liệu chính thức

- [Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html).
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html).
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [JEP 454 — Foreign Function & Memory API được hoàn thiện ở JDK 22](https://openjdk.org/jeps/454).

**Kết luận:** **SegmentAllocator** quyết định cách cấp view/vùng nhớ theo yêu cầu, **MemoryLayout** quyết định size/alignment còn **Arena** quản ownership/lifetime. **slicingAllocator** tốt cho nhiều đối tượng cùng sống trong slab, **prefixAllocator** cho scratch reuse tuần tự, **asSlice** cho view có bounds hẹp trên một backing lớn. Muốn tiết kiệm native RAM thật sự, phải quản **kích thước backing, số buffer in flight và thời điểm giải phóng**, không chỉ tạo nhiều slice.
