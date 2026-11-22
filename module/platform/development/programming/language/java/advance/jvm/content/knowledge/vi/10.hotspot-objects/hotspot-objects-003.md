# Đầu đối tượng, dữ liệu trường, căn chỉnh và phần đệm trong HotSpot JVM

Một **object Java** không chỉ chiếm đúng tổng số byte của các field được khai báo trong source. Trong một cách bố trí phổ biến của **HotSpot JVM**, một instance trên Java heap gồm **object header** (đầu đối tượng), **instance field data** (dữ liệu các trường thuộc đối tượng) và có thể có **padding** để đáp ứng các ràng buộc **alignment**. Với array, header còn cần lưu **độ dài mảng**. Cách bố trí thật phụ thuộc JVM, phiên bản JDK, kiến trúc 32/64-bit, compressed references, tùy chọn căn chỉnh và các cơ chế như **Compact Object Headers**.

Bài học tập trung vào **biểu diễn vật lý trong HotSpot**, không nên nhầm với hợp đồng trừu tượng của Java Language Specification (JLS): đặc tả Java quy định ngữ nghĩa field, object, array và memory model, nhưng **không buộc mọi JVM dùng một số byte header hoặc một thứ tự field giống nhau**.

Mục tiêu sau khi đọc:

1. Giải thích **mark word**, **class pointer/klass word**, và **array length** trong object header.
2. Phân biệt field instance, field static, object reference và object được tham chiếu.
3. Tính được các ví dụ object size minh họa khi đã **nêu rõ giả định**.
4. Hiểu **internal padding**, **external/tail padding**, alignment và ảnh hưởng đến bộ nhớ khi có hàng triệu object.
5. Biết **compressed oops** khác **compressed class pointers** như thế nào.
6. Dùng Java 17+ và công cụ như **Java Object Layout (JOL)** hoặc `Instrumentation.getObjectSize` để quan sát, thay vì đoán từ source.
7. Nhận diện các cấu hình HotSpot mới có **compact headers** để không áp dụng cứng sơ đồ cũ.

## 1. Mô hình tổng quát của một object

Sơ đồ **minh họa** cho object thông thường trên một HotSpot 64-bit với kiểu header cổ điển:

```text
Địa chỉ tăng dần →
┌───────────────────────────────────┐
│ Object header                     │
│   mark word                       │
│   klass / class pointer           │
├───────────────────────────────────┤
│ Instance fields                   │
│   primitive values                │
│   reference values                │
│   ...                             │
├───────────────────────────────────┤
│ Padding nếu cần                   │
└───────────────────────────────────┘
```

Với một mảng, có thêm thông tin số phần tử:

```text
┌───────────────────────────────────┐
│ Header: mark + class information  │
│ Array length (int)                │
├───────────────────────────────────┤
│ Array elements [0 .. length-1]    │
├───────────────────────────────────┤
│ Padding nếu cần                   │
└───────────────────────────────────┘
```

**Đây không phải layout tuyệt đối.** HotSpot có thể sắp xếp field theo chiến lược riêng, dùng compact header, nén các con trỏ khác nhau hoặc thay đổi cách đặt metadata. Sơ đồ chỉ giúp phân chia trách nhiệm.

### Thuật ngữ quan trọng

| Thuật ngữ | Diễn giải |
| --- | --- |
| **object header** | Phần thông tin để VM quản lý object, định danh kiểu và trạng thái liên quan |
| **mark word** | Word metadata về trạng thái object; cách mã hóa thay đổi theo JDK, khóa đồng bộ, GC và header mode |
| **klass word / class pointer** | Thông tin định danh runtime class/metadata class của object trong header cổ điển |
| **instance field data** | Giá trị các instance fields, gồm primitive values hoặc references |
| **internal padding / gap** | Byte trống/chưa dùng giữa các thành phần do field alignment/layout |
| **external/tail padding** | Byte chèn vào cuối object để tổng kích thước đạt object alignment |
| **object alignment** | Ràng buộc kích thước/địa chỉ object theo đơn vị căn chỉnh triển khai |
| **shallow size** | Kích thước của **chính object**, không đi theo các references để tính object graph |
| **retained size** | Bộ nhớ có thể giải phóng nếu object là dominator của các objects khác, tùy công cụ/phân tích heap |

**Reference không phải object data của object đích.** Nếu `Node` có field `Node next`, body của `Node` chứa một **reference value**; các field của object `next` nằm trong **object khác**. Vì vậy không thể cộng toàn bộ chuỗi node vào shallow size của node đầu.

## 2. Object header trong HotSpot: thành phần và nhiệm vụ

### 2.1. Mark word

Trong mô hình header HotSpot truyền thống, **mark word** giữ những thông tin phục vụ quản lý trạng thái object, liên quan đến:

- **Identity hash code**, khi nó được tính/ghi nhận theo chiến lược VM.
- **Locking/synchronization state**, tùy cơ chế monitor và phiên bản HotSpot.
- **GC age** hoặc thông tin đánh dấu/trạng thái thích hợp.
- Một số **bit trạng thái** khác; bit layout có thể khác ở các thế hệ JDK.

Mark word **không đơn giản là một trường Java `int hash`** mà lập trình viên thấy qua reflection. Nó là dữ liệu nội bộ của JVM. Mọi đối tượng có thể mang các thông tin cần thiết để triển khai `Object.hashCode()`/identity semantics và `synchronized`, nhưng **không phải mỗi object ngay khi cấp phát đều có một identity hash đã được tính sẵn**.

```java
Object x = new Object();
int h = System.identityHashCode(x);
```

Đây là đoạn mã minh họa trong method; `System.identityHashCode` yêu cầu identity hash của object và có thể làm thay đổi trạng thái metadata/đường lưu thông tin phù hợp với VM. **Giá trị hash không phải địa chỉ bộ nhớ** và không được bảo đảm là duy nhất cho tất cả objects.

### 2.2. Klass pointer / class word

Ở layout truyền thống, header còn chứa **thông tin trỏ tới runtime class metadata** (thường gọi `klass` pointer hoặc class word). Điều này giúp JVM biết:

- Object thuộc runtime class/interface/array type nào.
- Kích thước/layout thích hợp của object và đường truy cập metadata.
- Những thông tin hỗ trợ method dispatch, type checks, GC scanning và nhiều tác vụ nội bộ.

Đây **không phải nhất thiết là Java field `Class<?> clazz` lưu ngay trong object**. `obj.getClass()` cho ra **`java.lang.Class` mirror** thích hợp, nhưng VM class metadata và mirror là những cấu trúc liên quan mà không nên đồng nhất về địa chỉ/layout.

Hai instances cùng class có thể dùng chung class metadata, nhưng **mỗi instance có phần đầu riêng** theo header mode đang dùng.

### 2.3. Kích thước header phụ thuộc mode

Một cấu hình thường dùng để giảng giải **HotSpot 64-bit JDK 17**, với compressed class pointers bật, là:

```text
Normal instance (classic header):
offset 0..7   : mark word      8 byte
offset 8..11  : class pointer  4 byte (compressed)
---------------------------------------
Total header                   12 byte
```

Nếu **không nén class pointer**, ở mode cổ điển class word có thể rộng **8 byte**, và header thường là **16 byte** trong một HotSpot 64-bit tương ứng.

**Những con số này là ví dụ triển khai theo cấu hình, không phải kích thước object bắt buộc của mọi Java 17/JDK.** Heap alignment, architecture, header mode và các thành phần bổ sung còn quyết định shallow size cuối cùng.

### 2.4. Compact Object Headers: đừng cố định 12 hoặc 16 byte cho mọi JDK mới

Dự án **OpenJDK Lilliput** nghiên cứu và triển khai các phương án giảm overhead của object headers. Trong các JDK mới:

- **JDK 24** giới thiệu **Compact Object Headers (Experimental)** theo **JEP 450**.
- **JDK 25** đưa tính năng này sang dạng sản phẩm có thể bật theo **JEP 519**.
- Với compact headers trên HotSpot 64-bit được hỗ trợ, thông tin class và metadata đánh dấu có thể được kết hợp vào một cấu trúc header **8 byte**, thay vì hai phần 8 + 4 hoặc 8 + 8 byte của bố trí cổ điển.
- Tùy chọn `-XX:+UseCompactObjectHeaders` và trạng thái mặc định/hỗ trợ có thể thay đổi theo JDK/vendor; **hãy kiểm tra JDK hiện dùng** thay vì mặc định luôn bật hoặc tắt.

Vì vậy phát biểu **“mọi Java object luôn có header 12 byte”** vừa không đúng với các mode 32-bit/không nén, vừa không còn áp dụng phổ quát cho HotSpot có compact headers.

Tác dụng của header nhỏ là giảm overhead trên **số lượng object rất lớn**, tăng mật độ heap/cache và đôi khi cải thiện performance. Nó **không làm biến mất** instance fields, object alignment hay các quy tắc ngữ nghĩa của Java.

## 3. Instance fields: giá trị nào thực sự nằm trong object?

Xét class:

```java
class Record {
    byte active;
    int count;
    long total;
    Object owner;
    static int globalCounter;
}
```

Đây là **class minh họa có thể đặt trong `Record.java`**, không phải một chương trình với `main`. Bốn trường `active`, `count`, `total`, `owner` là **instance fields**; `globalCounter` là **static field**.

| Trường | Có thuộc instance body không? | Thông tin |
| --- | --- | --- |
| `byte active` | Có | Giá trị primitive `byte` |
| `int count` | Có | Giá trị primitive `int` |
| `long total` | Có | Giá trị primitive `long` |
| `Object owner` | Có | **Reference** tới object khác, không chứa toàn bộ object đó |
| `static int globalCounter` | **Không** | Trạng thái thuộc runtime class, không cộng một lần cho mỗi instance |

**Không được nhầm `static` với “nằm trong stack”.** Static fields gắn với runtime class và cơ chế lưu trữ của JVM, không phải biến instance, cũng không bị sao chép thành một field riêng trong mỗi object.

### 3.1. Kích thước primitive theo ngữ nghĩa và theo layout

| Kiểu | Độ rộng dữ liệu primitive của Java | Kích thước field phổ biến trong HotSpot |
| --- | --- | --- |
| `boolean` | Boolean logic, không có quy định JLS buộc field là 1 byte | Thường 1 byte cho field; arrays/VM mode có quy tắc triển khai |
| `byte` | 8 bit | 1 byte |
| `short` | 16 bit | 2 byte |
| `char` | 16 bit unsigned UTF-16 code unit | 2 byte |
| `int` | 32 bit | 4 byte |
| `float` | 32 bit | 4 byte |
| `long` | 64 bit | 8 byte |
| `double` | 64 bit | 8 byte |
| Reference | Tham chiếu tới object hoặc null | Thường 4 byte khi compressed oops, có thể 8 byte khi uncompressed |

Bảng “thường” nói về **cách HotSpot đặt dữ liệu**. Nó không khẳng định tổng shallow size chỉ cần cộng các con số ấy: còn header, field alignment, object alignment, inherited fields và layout choices.

### 3.2. Không phải thứ tự field trong RAM giống thứ tự source

Ví dụ:

```java
class Mixed {
    byte a;
    long b;
    byte c;
    int d;
}
```

Các source fields xuất hiện theo thứ tự `a, b, c, d`, nhưng HotSpot có thể **sắp xếp lại offsets** hoặc tận dụng các gaps để giảm padding. Không có lời hứa Java language rằng `b` bắt buộc bắt đầu ngay sau `a` ở bộ nhớ vật lý. Những thao tác `getfield`/`putfield` vẫn đúng vì JVM biết layout runtime của class.

Field layout chịu ảnh hưởng các yếu tố:

- Kích thước/alignment từng field.
- Superclass đã có phần instance fields.
- Compressed reference/class pointer mode.
- Thuật toán field layout của phiên bản HotSpot.
- Sự khác biệt đối với contended fields hoặc các thay đổi runtime nâng cao.

**Do đó đừng tự đoán offset rồi dùng như ABI ổn định**. Java reflection có thể lấy field theo tên nhưng không cung cấp hợp đồng public về raw byte offset của nó.

### 3.3. Instance fields được kế thừa vẫn góp phần vào object

```java
class Parent {
    int parentCount;
}

class Child extends Parent {
    long childTotal;
}
```

Một **instance `Child`** cần lưu cả trạng thái instance kế thừa của `Parent` lẫn field của `Child`, cộng header/padding. **Không có hai object headers độc lập** cho parent part và child part khi đây là một instance `Child`.

`new Child()` tạo **một object** runtime class `Child`, không tạo một `Parent` object riêng bên trong theo nghĩa hai allocations. Parent constructor được gọi trong constructor chain để khởi tạo phần field của object đó.

## 4. Alignment: vì sao object có thể lớn hơn tổng field widths?

**Alignment** là yêu cầu căn chỉnh địa chỉ/kích thước object theo một đơn vị nhất định của VM. Trên HotSpot 64-bit thường gặp cấu hình **8-byte object alignment**, nhưng `-XX:ObjectAlignmentInBytes` có thể thay đổi alignment theo những giá trị được hỗ trợ.

Khi tổng phần header + fields không chia hết cho alignment, JVM có thể cần **padding**.

Công thức minh họa:

```text
rawSize      = headerBytes + fieldRegionBytes + layoutGapsBytes
alignedSize  = roundUp(rawSize, objectAlignment)

roundUp(n, a) = ((n + a - 1) / a) * a
```

Trong công thức, phép chia là chia nguyên với `a > 0`; chỉ dùng để giải bài toán sau khi **đã biết** layout. Nếu JVM sắp lại fields hoặc dùng compact headers, đầu vào công thức phải đổi theo.

### 4.1. Ví dụ object có một `int`

Giả sử:

- HotSpot 64-bit, classic header **12 byte** (mark 8 + compressed klass 4).
- `int` đặt ngay sau header, chiếm **4 byte**.
- Object alignment = **8 byte**.
- Không có phần gap khác.

```text
offset  0.. 7 : mark word       8 B
offset  8..11 : class word      4 B
offset 12..15 : int value       4 B
-------------------------------
raw / aligned size            16 B
```

Một object chỉ có **4 byte dữ liệu field** trong mô hình này vẫn tốn **16 byte shallow size** vì phải lưu header.

### 4.2. Ví dụ object không có instance field

Vẫn với classic header 12 B và alignment 8 B:

```text
offset  0.. 7 : mark word             8 B
offset  8..11 : class word            4 B
offset 12..15 : tail padding          4 B
-----------------------------------------
shallow size                       16 B
```

Tổng header 12 được làm tròn lên **16 B**. Do đó “`new Object()` không có field thì chiếm 0 byte” là sai. Nhưng **16 B không phải universal object size**; có cấu hình header compact làm ví dụ khác đi.

### 4.3. Ví dụ với `long` và một gap

Giả sử 12-byte classic header, một field `long` chiếm 8 B và phải đặt tại offset bội số của 8:

```text
offset  0.. 7 : mark word             8 B
offset  8..11 : class word            4 B
offset 12..15 : alignment gap         4 B
offset 16..23 : long value            8 B
-----------------------------------------
total                                24 B
```

Với class chỉ có một `long`, đây là một layout **minh họa hợp lý** trên HotSpot 64-bit cổ điển. Không lấy đó làm bằng chứng một JVM không bao giờ đổi thứ tự hoặc chèn field khác vào gap. Khi có nhiều fields, VM có thể tận dụng khoảng trống thay vì để toàn bộ mất mát.

### 4.4. Ví dụ field packing

Giả sử layout có header 12 B, cần đặt một `int` và một `long`. Nếu `int` lấp vị trí 12..15 trước `long` tại 16..23 thì tổng là **24 B**:

```text
[header 12][int 4][long 8] → 24 B
```

Nếu layout khác làm phát sinh gap bổ sung, tổng có thể cao hơn. Chính vì thế **thứ tự placement quan trọng**, nhưng Java source không cam kết thứ tự raw offsets. Dùng JOL hoặc công cụ đáng tin cho **JVM đang thực thi** thay vì khẳng định mọi `int+long` luôn có kích thước bất biến.

## 5. Padding gồm những dạng nào?

| Loại | Vị trí | Nguyên nhân |
| --- | --- | --- |
| **Header-to-field gap** | Giữa header và field đầu | Field cần alignment chặt hơn offset sau header |
| **Internal padding** | Giữa các fields | Field layout/alignment để đặt field tiếp theo |
| **Tail/external padding** | Cuối object | Căn tổng object size lên bội số alignment |
| **Array padding** | Sau các elements cuối hoặc khoảng trước element đầu | Element base offset / tổng kích thước mảng cần căn chỉnh |

Các bytes padding **không phải** fields Java; reflection thông thường không trả về chúng như một `Field`. Tùy VM, nội dung byte padding không nên được suy diễn thành dữ liệu có ý nghĩa. Không thiết kế chương trình phụ thuộc chúng chứa toàn zero hoặc giữ giá trị ổn định qua GC.

### Vì sao padding quan trọng khi ứng dụng có hàng triệu objects?

Giả sử có **1.000.000 objects** và một thay đổi layout giúp giảm average shallow size **8 byte/object**:

```text
1,000,000 × 8 byte = 8,000,000 byte
```

Tương đương khoảng **7,63 MiB** dữ liệu theo phép quy đổi nhị phân. Đây chỉ là **bài toán ước tính footprint shallow**; tổng memory retained còn phụ thuộc references, object graph, arrays, allocator/GC overhead và runtime khác.

Khi dữ liệu nhỏ nhưng mỗi item là một object riêng, tỷ lệ header + padding có thể lớn. Ví dụ **một triệu box objects** chứa primitive value riêng có thể có overhead cao hơn dùng **một primitive array** nếu yêu cầu truy cập/đồng bộ cho phép. Không nên tối ưu mọi chương trình sang primitive arrays bất chấp semantics, nhưng hiểu layout giúp thấy khác biệt.

## 6. Reference fields: compressed oops và compressed class pointers

### 6.1. Hai kiểu con trỏ khác vai trò

**Compressed ordinary object pointers (compressed oops)** là cơ chế HotSpot 64-bit có thể biểu diễn reference tới object trong một số vị trí bằng giá trị ngắn hơn, thường **4 byte**, thay vì raw native pointer 8 byte.

**Compressed class pointers** là cơ chế riêng để biểu diễn tham chiếu từ header/class metadata theo cách thu gọn, thường **4 byte trong classic header**. Hai cơ chế liên quan nhưng **không phải một flag/khái niệm đồng nhất**.

| Trường hợp | Cái được nén (mô hình cổ điển) | Ví dụ nơi quan sát |
| --- | --- | --- |
| Compressed oops | Reference values tới Java objects | Field `Object child`, elements của `Object[]` |
| Compressed class pointers | Tham chiếu đến class metadata trong object header | Class/klass word của ordinary object |
| Compact Object Headers | Tổ chức lại thông tin header, kết hợp metadata theo chế độ mới | Đầu object của các JDK hỗ trợ |

Việc chạy tiến trình Java 64-bit **không bắt buộc mọi reference field đều là 8 B**. Ngược lại, vì class có field `long` 8 B cũng không suy ra header đang dùng 8-byte class pointer.

### 6.2. `-XX:+UseCompressedOops` không biến `long` thành 4 byte

Nén object pointers chỉ tác động representation của các references phù hợp, **không rút `long` hoặc `double` từ 64 bit xuống 32 bit**. Kết quả biểu thức Java `long` vẫn có ngữ nghĩa chính xác theo JLS.

Thay đổi compressed oops có thể khiến shallow size của:

```java
class Node {
    Object left;
    Object right;
}
```

khác nhau, vì hai fields reference có thể có kích thước vật lý khác. Nhưng thứ tự field, header mode và padding cũng có thể tác động; không đơn giản cộng `2 × (8 - 4)` rồi khẳng định chắc chắn chênh 8 B cho mọi JVM.

### 6.3. Vì sao compressed references có lợi?

Một heap chứa rất nhiều object references có thể giảm footprint đáng kể khi references chiếm 4 B thay vì 8 B. Lợi ích thường gặp:

- Ít byte hơn cho fields và arrays chứa references.
- Dữ liệu vừa cache CPU tốt hơn, có thể giúp locality.
- Một số trường hợp giảm áp lực bộ nhớ, GC và bandwidth.

Đổi lại JVM cần logic **decode/encode** references và bị ảnh hưởng bởi dải heap được address bằng compressed scheme; lựa chọn bật/tắt thường do ergonomics, heap size và VM flags quyết định.

Với JDK 17 HotSpot, có thể kiểm tra các flags thực tế:

```bash
java -XX:+PrintFlagsFinal -version
```

Tìm `UseCompressedOops`, `UseCompressedClassPointers` và `ObjectAlignmentInBytes`. **Đây là HotSpot flags**, có thể đổi/bị deprecate ở các JDK mới; xem bản JDK bạn đang chạy thay vì chép flag từ blog cũ.

## 7. Mảng: header, length và phần tử liền kề theo layout JVM

Mảng Java là objects có **length cố định**. Cùng một array class `int[].class` có thể có các instances dài 0, 3 hoặc 1.000; length thuộc **array object**, không phải type `int[]`.

Trong layout cổ điển **HotSpot 64-bit với compressed class pointer**, một mô hình thường gặp cho mảng là:

```text
offset  0.. 7 : mark word       8 B
offset  8..11 : klass word      4 B
offset 12..15 : array length    4 B
offset 16..   : elements
...           : padding tùy tổng size
```

Vì vậy array header minh họa có **16 byte** trước vùng phần tử. Đây **không phải** quy tắc bắt buộc cho compact headers, mode không nén hoặc các kiến trúc JVM khác. Trong một số mode, có gap giữa length và elements để đảm bảo alignment của phần tử, nhất là với element type rộng.

### 7.1. Ví dụ `int[]` và alignment 8 B

Với giả định header 16 B, mỗi phần tử `int` 4 B, object alignment 8 B:

| Mảng | Header | Elements | Raw size | Aligned size |
| --- | ---: | ---: | ---: | ---: |
| `new int[0]` | 16 B | 0 B | 16 B | 16 B |
| `new int[1]` | 16 B | 4 B | 20 B | 24 B |
| `new int[2]` | 16 B | 8 B | 24 B | 24 B |
| `new int[3]` | 16 B | 12 B | 28 B | 32 B |
| `new int[4]` | 16 B | 16 B | 32 B | 32 B |

**Đây là tính toán theo giả định**, không phải kết quả `getObjectSize` được bảo đảm trên mọi HotSpot. Nếu alignment đổi thành 16 B hoặc array header đổi, kết quả phải tính lại.

### 7.2. `Object[]` khác `int[]`

Với `Object[]`, mỗi element là một **reference value**, có thể chiếm 4 B khi compressed oops bật hoặc 8 B khi tắt. **Nội dung của object mà reference trỏ tới không nằm bên trong phần tử mảng theo nghĩa layout shallow**.

```java
Object[] arr = new Object[2];
arr[0] = new byte[1024];
arr[1] = "hello";
```

Đây là đoạn code minh họa trong method. Shallow size của `arr` gồm header + **hai slots reference** + padding. Nó **không** cộng thêm 1.024 bytes của array `byte[]` và dữ liệu `String`. Muốn biết tổng object graph cần công cụ đo deep/retained size hoặc phân tích đồ thị references.

### 7.3. Mảng nhiều chiều thực chất là mảng của mảng

```java
int[][] matrix = new int[2][3];
```

Trong mô hình Java, đây là **một outer array** chứa references đến **hai inner int[] arrays**. Tổng memory không bằng một header 16 B cộng `2 × 3 × 4` mà thôi: mỗi inner `int[]` cũng là object với **header và padding riêng**.

```text
outer int[][]  ──►  [ ref0 | ref1 ]
                        │      │
                        ▼      ▼
                     int[3]  int[3]
                      object  object
```

Hai inner arrays là các objects khác nhau, cho phép từng hàng có độ dài khác nhau. Nếu tạo `new int[2][]`, outer array được cấp phát nhưng hai references ban đầu là `null`, không có inner arrays cho tới khi chương trình tạo chúng.

## 8. Tính shallow size đúng: đo gì và không đo gì?

**Shallow size** biểu diễn bộ nhớ dành cho một object đơn lẻ theo đo lường của một JVM/tool. Nó thường bao gồm header, instance fields hoặc array elements, gaps và tail padding; không đệ quy sang những object khác được tham chiếu.

**Deep size** thường là tổng kích thước của object graph reachable theo định nghĩa công cụ; **retained size** là kích thước memory có thể được giải phóng nếu object và toàn bộ các objects chỉ còn reachable qua nó không còn reachable. Hai khái niệm này không đồng nghĩa:

```text
A ──────► B ◄────── C
```

Nếu `B` còn reachable qua `C`, bỏ `A` không giải phóng `B`. Vậy `A` có thể “deep traverse” tới `B`, nhưng không nhất thiết **retain** `B` theo thuật toán dominator.

### Ví dụ node có reference

```java
class Node {
    int value;
    Node next;
}
```

Shallow size của `new Node()` gồm header, `int`, reference `next` và padding. Một danh sách 1.000 nodes có footprint đến từ **1.000 objects** riêng, mỗi node có header và alignment overhead; có thể còn allocation/GC metadata ở mức vùng heap. Không được lấy shallow size của node rồi khẳng định chính xác retained size của toàn bộ danh sách khi có các references từ nơi khác.

### `String` và collection còn có cấu trúc phụ

Một `String` object trong HotSpot hiện đại thường có fields để đại diện dữ liệu ký tự, và dữ liệu thực có thể ở một **array object khác**. `ArrayList` cũng có thể tham chiếu tới backing array. Vì vậy đo shallow size của `String` hoặc `ArrayList` **không tự đo toàn bộ payload**. Cấu trúc private fields của JDK có thể thay đổi theo release; dùng heap profiler hoặc JOL đúng phiên bản thay vì dựa vào layout trích từ một JDK cũ.

## 9. Identity hash, synchronized và GC có làm đổi layout không?

Các tính năng runtime tương tác với header/metadata nhưng không nên đồng nhất chúng với Java fields:

- **`System.identityHashCode(obj)`:** yêu cầu identity hash theo luật VM. Phương thức này không trả địa chỉ object và giá trị có thể trùng giữa hai objects.
- **`synchronized(obj)`:** thực thi monitor enter/exit theo Java Memory Model. HotSpot có những cơ chế lightweight locking/inflation/monitor metadata khác nhau theo JDK. Không tự giả định một bit pattern “biased locking” cố định cho mọi HotSpot hiện tại.
- **Garbage collection:** object có thể di chuyển trong heap; collector cần xác định object size, fields nào là references và metadata hỗ trợ GC. Các thông tin đó có thể đến từ object header và metadata của runtime class.
- **Class loading/unloading:** class metadata và class mirrors được JVM quản lý; mỗi object không chứa bản sao đầy đủ bytecode hoặc method table.
- **Compact header mode:** sự thay đổi tổ chức header có thể ảnh hưởng cách metadata khóa/hash/GC được xử lý.

Không nên đọc raw mark word từ Java application bằng phép truy cập offset chưa kiểm chứng; kiểu hoạt động này phụ thuộc VM internals và có thể thay đổi khi GC, hash calculation, lock transitions hoặc JDK upgrade.

## 10. Quan sát HotSpot layout bằng Java Object Layout (JOL)

**JOL (Java Object Layout)** là dự án công cụ của OpenJDK dùng để quan sát object layout, offsets và kích thước trên JVM thực tế, hoặc mô phỏng một số cấu hình. Nó phù hợp hơn việc tự cộng field sizes thủ công nếu bạn cần kết quả của một JVM cụ thể.

Dự án: https://openjdk.org/projects/code-tools/jol/  
Repository và hướng dẫn CLI: https://github.com/openjdk/jol

Khi **đã cài/có JOL CLI phù hợp**, một lệnh ví dụ:

```bash
java -jar jol-cli.jar internals java.lang.Integer
```

`jol-cli.jar` là **tên tệp minh họa**; hãy thay bằng tên/đường dẫn JAR JOL bạn thật sự có. Một số bản JOL CLI phát hành dưới tên có phiên bản hoặc đuôi `-full.jar`. Không dùng lệnh trên khi chưa có JAR.

Output có thể bao gồm:

```text
OFF  SZ   TYPE   DESCRIPTION
0    8           (object header: mark)
8    4           (object header: class)
12   4    int    Integer.value

Instance size: 16 bytes
Space losses: ...
```

Đây là **mô tả mẫu rút gọn** cho một HotSpot 64-bit classic header compressed class pointers; không phải output `jol` luôn cố định. Nếu chạy trên JDK với compact headers hoặc flags khác, offsets/instance size có thể khác.

### Đọc `OFF`, `SZ`, `Instance size` và `Space losses`

- **`OFF`:** offset byte từ đầu object trong layout được trình bày.
- **`SZ`:** kích thước mục tương ứng (byte).
- **`DESCRIPTION`:** header, field, array element hoặc padding/gap.
- **`Instance size`:** shallow size của instance theo phép đo/mô hình công cụ.
- **`Space losses`:** những byte không dùng do gaps/tail padding theo báo cáo.

JOL có thể yêu cầu quyền/agent phù hợp để truy cập layout chính xác trên các JDK mới. Nếu một chế độ tool chỉ đưa ra **estimate/simulation**, hãy ghi rõ đó **không phải measurement chắc chắn của mọi live object**.

### Không nhầm object header và field offsets với source field ordering

Khi JOL in field `long b` ở offset 16 dù `byte a` khai báo trước, điều đó không cho phép chương trình phụ thuộc offset 16 như ABI public. Layout là hợp đồng nội bộ của HotSpot đang sử dụng và có thể thay đổi sau lần khởi chạy với flags khác hoặc JDK upgrade.

## 11. Ví dụ Java 17+ độc lập: phân biệt object, class, field và array

Tạo file **`ObjectLayoutBasics.java`**:

```java
public class ObjectLayoutBasics {
    static class Empty {}

    static class Data {
        byte flag = 1;
        int number = 42;
        Object reference = new Object();
        static int shared = 100;
    }

    static class Parent {
        int parentValue = 7;
    }

    static class Child extends Parent {
        long childValue = 9L;
    }

    public static void main(String[] args) {
        Data first = new Data();
        Data second = new Data();
        int[] array = new int[3];
        Child child = new Child();

        System.out.println("different instances: " + (first != second));
        System.out.println("same class: "
                + (first.getClass() == second.getClass()));
        System.out.println("flag and number: "
                + first.flag + ", " + first.number);
        System.out.println("different nested objects: "
                + (first.reference != second.reference));
        System.out.println("static shared: " + Data.shared);
        System.out.println("instance fields declared: "
                + Data.class.getDeclaredFields().length);
        System.out.println("empty declared fields: "
                + Empty.class.getDeclaredFields().length);
        System.out.println("child fields: "
                + child.parentValue + ", " + child.childValue);
        System.out.println("array length: " + array.length);
        System.out.println("array class name: "
                + array.getClass().getName());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ObjectLayoutBasics.java
java ObjectLayoutBasics
```

**Standard output chính xác:**

```text
different instances: true
same class: true
flag and number: 1, 42
different nested objects: true
static shared: 100
instance fields declared: 4
empty declared fields: 0
child fields: 7, 9
array length: 3
array class name: [I
```

### Diễn giải

1. `new Data()` tạo các instances riêng, nhưng cả hai có cùng runtime class.
2. `Data.shared` là **static field**, không chiếm một slot instance body riêng cho từng `Data`. Tuy nhiên `getDeclaredFields()` liệt kê **cả static và instance fields**, nên `Data` có **4 declared fields**; số này **không phải số instance fields**.
3. `reference = new Object()` tạo một **object khác cho mỗi Data** trong ví dụ; Data chỉ lưu reference tới object đó. Shallow size của Data không cộng cả object `reference` chỉ vì nó reachable.
4. `Child` có thể truy cập `parentValue` từ superclass và `childValue` của chính nó; trong một Child instance, đó là các fields của cùng một object.
5. Mảng `int[3]` có một array header, ba phần tử `int` và padding tùy layout. `[I` là tên runtime kiểu mảng `int[]` theo cách `Class.getName()` biểu diễn.

Bài demo **không in địa chỉ hay shallow size**, vì Java SE API thông thường không cam kết raw object layout. Bài thí nghiệm ở mục sau dùng `Instrumentation` để đo bằng JVM thật.

## 12. Đo shallow size với `Instrumentation.getObjectSize`

Java Instrumentation API có phương thức `getObjectSize(Object)` cho phép lấy **ước lượng phụ thuộc triển khai về bộ nhớ dành cho một object**. Nó yêu cầu **Java agent** có `premain` được cung cấp qua `-javaagent`; không cần dùng API nội bộ `sun.misc.Unsafe` hay giả định offset header.

Phương thức này **không tính tổng mọi object reachable** từ object được đo, và kết quả không phải một ABI/GC retained-size contract bất biến.

### 12.1. Tạo agent `ShallowSizeAgent.java`

```java
import java.lang.instrument.Instrumentation;

public class ShallowSizeAgent {
    private static Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
    }

    public static long sizeOf(Object value) {
        if (instrumentation == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        return instrumentation.getObjectSize(value);
    }
}
```

### 12.2. Tạo chương trình `SizeExperiment.java`

```java
public class SizeExperiment {
    static class Empty {}

    static class OneInt {
        int value;
    }

    static class OneLong {
        long value;
    }

    static class HasReference {
        Object child = new byte[1000];
    }

    private static void show(String name, Object value) {
        System.out.println(name + " shallow: "
                + ShallowSizeAgent.sizeOf(value));
    }

    public static void main(String[] args) {
        show("Empty", new Empty());
        show("OneInt", new OneInt());
        show("OneLong", new OneLong());
        show("HasReference", new HasReference());
        show("int[0]", new int[0]);
        show("int[3]", new int[3]);
        show("byte[1000]", new byte[1000]);
    }
}
```

### 12.3. Tạo manifest cho agent

Tạo file văn bản UTF-8/ASCII tên **`manifest.mf`**:

```text
Premain-Class: ShallowSizeAgent

```

Cần có **dòng trống cuối manifest** theo cấu trúc JAR manifest. Tại thư mục chứa các file trên, chạy:

```bash
javac -encoding UTF-8 ShallowSizeAgent.java SizeExperiment.java
jar cfm shallow-agent.jar manifest.mf ShallowSizeAgent.class
java -javaagent:shallow-agent.jar SizeExperiment
```

Nếu tên file JAR khác, thay tương ứng. `-javaagent` là cơ chế Java Instrumentation API chuẩn; hai class demo không cần thư viện ngoài.

### 12.4. Kết quả và cách đọc

Chương trình in 7 dòng với dạng:

```text
Empty shallow: <bytes>
OneInt shallow: <bytes>
OneLong shallow: <bytes>
HasReference shallow: <bytes>
int[0] shallow: <bytes>
int[3] shallow: <bytes>
byte[1000] shallow: <bytes>
```

**Đây là mẫu format, không phải stdout chính xác**: giá trị `<bytes>` do JVM thực tế quyết định. Với cấu hình HotSpot 64-bit classic header + compressed pointers + alignment 8 B, bạn **có thể** thấy các kích thước tương ứng các mô hình tính ở mục 4/7. Nếu JDK bật compact headers hoặc alignment khác, số đo có thể thay đổi.

Các điều cần kiểm tra từ phép đo:

- `Empty` có shallow size **khác 0** do object header/alignment.
- `HasReference` chỉ bao gồm **field reference**, không cộng toàn bộ `byte[1000]` được tham chiếu.
- `byte[1000]` là **array object khác**, có header + 1000 phần tử + padding.
- `int[3]` có thêm phần tử so với `int[0]`, nhưng thay đổi sau alignment có thể không đúng chính xác 3 × 4 B.
- `OneLong` và `OneInt` có thể bằng hoặc khác shallow size tùy header/gaps/alignment; không kết luận chỉ từ primitive width.

**Vì sao không ghi một bộ stdout số cố định?** `getObjectSize` trả *implementation-specific approximation*, JVM implementations và options có thể làm output khác. Một README chất lượng phải phân biệt **mẫu hợp lệ** với **kết quả chắc chắn**.

### 12.5. Thử đổi alignment để đối chiếu

Với HotSpot JDK 17 hỗ trợ flag:

```bash
java -XX:ObjectAlignmentInBytes=16 -javaagent:shallow-agent.jar SizeExperiment
```

Khi đổi object alignment, một số shallow sizes có thể tăng vì tổng object phải được làm tròn theo bội số lớn hơn. Đừng chạy flag này một cách mù quáng trên ứng dụng production; bài thực hành chỉ dành cho tiến trình test và flag có thể ảnh hưởng heap ergonomics.

Muốn thử mode compressed oops, trước hết **kiểm tra flags của phiên bản JDK hiện dùng**. Không giả định cùng tham số luôn được hỗ trợ hoặc có cùng hiệu quả sau thay đổi lớn ở layout JVM.

## 13. Đo layout khác heap profiler: công cụ nào trả lời câu hỏi nào?

| Câu hỏi | Công cụ gợi ý | Giới hạn |
| --- | --- | --- |
| Object có fields nào, offsets và padding gì? | **JOL** | Phụ thuộc VM/JDK/options; có thể cần agent để xác minh |
| Một object chiếm khoảng bao nhiêu byte shallow? | **Instrumentation.getObjectSize** | Estimate tùy triển khai, không tính referenced graph |
| Object class nào đang chiếm nhiều heap? | `jcmd PID GC.class_histogram`, heap profiler | Histogram thường tổng theo class, không trình bày layout từng object |
| Những object nào giữ data không được GC? | Heap dump + dominator tree | Cần hiểu GC roots/retained size, heap dump có thể tốn tài nguyên |
| Heap và native footprint hiện tại? | JVM metrics, JMX, NMT, OS monitoring | Không trộn reserved/committed/RSS/shallow |
| Header mode/heap alignment ra sao? | HotSpot flags, JOL VM details | Không dùng giả định từ máy khác |

Ví dụ chẩn đoán JDK 17 HotSpot:

```bash
java -XX:+PrintFlagsFinal -version
jcmd -l
jcmd PID GC.class_histogram
```

Trong dòng cuối, **thay `PID` bằng số process thực**; không chạy ở môi trường production tùy tiện vì class histogram có thể gây chi phí thời gian/safepoint. Với một ứng dụng đơn giản muốn biết offset/field packing, **JOL** thường phù hợp hơn histogram.

### Không dùng `Runtime.totalMemory()` để suy object size chính xác

`Runtime.getRuntime().totalMemory() - freeMemory()` gần đúng heap đang sử dụng theo snapshot, nhưng việc cấp phát một object có thể trùng thời điểm GC/TLAB refill/class loading hoặc allocation khác. Lấy chênh lệch hai lần gọi không phải phép đo shallow size chính xác. Để nghiên cứu layout, ưu tiên instrumentation/JOL.

## 14. False sharing, `@Contended` và overhead padding nâng cao

Đôi khi lập trình concurrency muốn **tăng khoảng cách bộ nhớ** giữa các fields hay counters để giảm **false sharing** giữa CPU cores. HotSpot có các cơ chế/annotation nội bộ như `@Contended` và các flag hỗ trợ theo phiên bản, có thể đưa **padding có chủ đích** vào object layout.

Điều này trái mục tiêu “packing nhỏ nhất”, nhưng có thể cải thiện throughput ở một số workload nhiều thread. Không nên vội coi mọi byte padding là lỗi thiết kế cần loại bỏ:

- **Alignment padding** phục vụ bố trí dữ liệu hợp lệ/hiệu quả.
- **Contended padding** có thể là chiến lược hiệu năng đối với dữ liệu chia sẻ giữa threads.
- Lợi ích của thay đổi phải được xác nhận bằng **benchmark đúng cách**; thêm padding khiến memory footprint tăng.

Trong JDK 17, `jdk.internal.vm.annotation.Contended` là API nội bộ module, không phải Java SE API thông thường. **Không khuyến khích** thêm vào code ứng dụng chỉ dựa trên bài này; cần đánh giá hỗ trợ, encapsulation và JDK version.

## 15. Object layout không quyết định tất cả về hiệu năng

Shallow size nhỏ hơn có thể giảm heap pressure, cache misses và GC work, nhưng **không tự bảo đảm** chương trình nhanh hơn. Một số yếu tố khác:

- **Object allocation rate**: bao nhiêu objects được tạo/giây.
- **Object lifetime**: objects chết sớm hay tồn tại lâu.
- **Memory locality**: dữ liệu truy cập liên tiếp hay qua đồ thị references.
- **Escape analysis/scalar replacement**: JIT có thể loại bỏ hoặc thay thế một số allocations vật lý khi bảo toàn ngữ nghĩa.
- **GC algorithm**: các collectors có cách quản lý regions/compaction và overhead riêng.
- **Synchronization**: lock contention và metadata runtime ảnh hưởng throughput.
- **Data structure choice**: `int[]` khác `List<Integer>` về boxing, references và khả năng cache locality.

**Điểm quan trọng khi benchmark:** nếu JIT chứng minh một object không cần được cấp phát vật lý trong đoạn code tối ưu, dùng một benchmark đơn giản với `new Object()` trong vòng lặp có thể không đo được object allocation mà người viết nghĩ đang đo. Dùng JMH/profiler khi đánh giá hiệu năng thực tế.

### Primitive array và boxed objects

So sánh:

```java
int[] values = new int[1000];
```

với:

```java
Integer[] boxed = new Integer[1000];
```

Trong array đầu, mỗi element giữ trực tiếp một giá trị `int`. Trong array thứ hai, mỗi element là một **reference** đến `Integer` object hoặc `null`, và các `Integer` objects riêng có overhead của chúng. Tuy nhiên không thể đơn giản nói mọi element `Integer[]` chắc chắn có object riêng, vì boxing caches/references sharing có thể xảy ra. Việc lựa chọn cấu trúc tùy semantics, nullability, API và performance.

## 16. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Object Java chỉ chiếm tổng kích thước fields.” | Còn header, layout gaps và padding |
| “`new Object()` không có field nên size bằng 0.” | Object vẫn có header và alignment overhead theo VM |
| “Mọi HotSpot 64-bit có header đúng 12 byte.” | Classic compressed 12 B là ví dụ; uncompressed/compact/JDK khác có layout khác |
| “Mark word là địa chỉ object.” | Mark word là metadata, không phải địa chỉ mà `identityHashCode` trả |
| “`identityHashCode` luôn duy nhất giữa mọi objects.” | Hash collisions có thể xảy ra, không dùng làm định danh tuyệt đối |
| “Klass pointer là instance field `Class<?> clazz`.” | Header dùng metadata nội bộ; class mirror là API liên quan, không phải field source |
| “Static field tốn thêm 4/8 B cho **mỗi** instance.” | Static state gắn với class, không phải phần field data riêng của mọi object |
| “`Object ref` chứa toàn bộ object đích.” | Nó chứa reference value tới một object khác |
| “`boolean` field luôn được JLS định nghĩa là 1 byte.” | Layout vật lý là chi tiết JVM; HotSpot phổ biến dùng 1 B cho field |
| “Field source order chính là byte offsets.” | HotSpot có thể sắp xếp/packing fields |
| “Object alignment chỉ ảnh hưởng performance, không ảnh hưởng size.” | Alignment làm tròn object size và có thể tăng padding |
| “Một `Child` object có hai headers vì có `Parent`.” | Một object runtime class Child chứa phần fields kế thừa, không hai allocations parent/child |
| “`int[][]` chỉ có một header.” | Mỗi outer/inner array là một object có header riêng |
| “`String` shallow size là toàn bộ memory của chuỗi.” | Payload có thể ở referenced array/object khác |
| “JOL output trên máy khác là ABI ổn định của Java.” | JVM/JDK/flags khác có thể đổi offsets/size |
| “`getObjectSize` đếm toàn bộ object graph.” | Nó đo **shallow estimate** của một object |
| “GC chắc chắn để lại object tại một địa chỉ cố định.” | Moving collectors có thể chuyển object; địa chỉ raw không là Java-level stable identity |
| “Compact headers làm object không cần metadata.” | Metadata được biểu diễn khác/thu gọn; JVM vẫn phải quản lý kiểu và trạng thái |

## 17. Bài tập và lời giải

### Bài 1 — Class trống

**Giả định:** HotSpot 64-bit classic compressed header 12 B, alignment 8 B, class không có fields.  
**Hỏi:** Shallow size minh họa?

**Đáp án:** `roundUp(12, 8) = 16 B`. Phần padding 4 B; không khẳng định JDK bật compact headers cũng có size này.

### Bài 2 — Một `int`

**Giả định:** cùng JVM ở bài 1; `int` được đặt tại offset 12.  
**Đáp án:** `12 + 4 = 16 B`, đã căn 8 B, không cần tail padding.

### Bài 3 — Một `long`

**Giả định:** mark 8 B + compressed class word 4 B, field `long` phải bắt đầu tại offset 16 và alignment 8 B.  
**Đáp án:** gap 4 B trước long, long 8 B, tổng **24 B**.

### Bài 4 — Mảng `int[3]`

**Giả định:** array header 16 B, mỗi int 4 B, alignment 8 B.  
**Đáp án:** raw 16 + 12 = 28 B; aligned **32 B**, 4 B tail padding.

### Bài 5 — Mảng `int[2]`

**Giả định:** như bài 4.  
**Đáp án:** 16 + 8 = **24 B**, chia hết 8; không cần tail padding.

### Bài 6 — Một mảng references

**Giả định:** array header 16 B, 3 elements references compressed 4 B, alignment 8 B.  
**Đáp án:** 16 + 3 × 4 = 28 B, aligned **32 B**. Không cộng shallow size của các objects được tham chiếu.

### Bài 7 — Static field

```java
class Example {
    int a;
    static int total;
}
```

**Hỏi:** Field `total` có làm shallow size mỗi `new Example()` tăng thêm một `int` không?  
**Đáp án:** Không. Nó gắn với runtime class, không phải mỗi instance.

### Bài 8 — Kế thừa

```java
class A { int a; }
class B extends A { int b; }
```

**Hỏi:** `new B()` có bao nhiêu object headers trong cùng object đó?  
**Đáp án:** Một theo mô hình HotSpot thông thường; parent fields và child fields thuộc một runtime object, không tạo thêm object A riêng.

### Bài 9 — Hai references

```java
class Holder {
    Object x;
    Object y;
}
```

**Hỏi:** Nếu cả hai fields trỏ cùng một object, shallow size Holder có giảm không?  
**Đáp án:** Không vì vẫn có hai field slots chứa references. Deep/retained analysis thay đổi theo aliasing và object graph.

### Bài 10 — Layout và phiên bản JDK

**Hỏi:** Kích thước `new Object()` quan sát bằng JOL trên HotSpot JDK 17 compressed header có bắt buộc giống HotSpot chạy Compact Object Headers ở JDK mới?  
**Đáp án:** Không. Header representation thay đổi; phải đo trên đúng JVM/configuration.

### Bài 11 — Byte padding

**Hỏi:** Có thể dùng reflection `getDeclaredField("padding")` để lấy tail padding tự động của object không?  
**Đáp án:** Không. Padding không là field Java khai báo trong class; công cụ layout mới trình bày nó.

### Bài 12 — Chẩn đoán heap

**Hỏi:** Heap profiler cho biết có hàng triệu `Node` objects. Có nên chỉ đo size của một `Node` rồi kết luận heap retained tổng cộng?  
**Đáp án:** Chưa. Cần xem references, arrays phụ, số lượng thực, object graph, dominators, GC roots và class loader để xác định bộ nhớ retained/allocated.

### Bài 13 — Reference field

**Hỏi:** Khi compressed oops bật, field `Object x` thường là 4 B. Nếu `x` trỏ tới `byte[1000]`, có phải `Holder` chứa hơn 1.000 B trong chính body?  
**Đáp án:** Không. `Holder` chứa reference field; array là object khác với header/payload riêng.

### Bài 14 — Alignment khác

**Giả định:** raw object size 20 B, alignment đổi từ 8 B thành 16 B.  
**Đáp án:** `roundUp(20, 8) = 24 B`; `roundUp(20, 16) = 32 B`. Đây là bài toán số học sau khi biết raw layout; JVM có thể thay layout khi đổi mode, nên số đo thực cần xác nhận.

## 18. Tổng kết

Mô hình nền tảng:

```text
Ordinary object (HotSpot layout khái quát):
    object header
  + instance field values
  + internal/tail padding
  = shallow footprint của object (theo VM)

Array object:
    array header + length metadata
  + array element slots
  + padding
  = shallow footprint của array

Object graph:
    nhiều objects/arrays liên kết bằng references
  → deep/retained size KHÔNG phải shallow size một object
```

**Mark word** phục vụ metadata trạng thái object, **class/klass information** giúp JVM xác định runtime type và layout; **field data** là giá trị instance riêng, không chứa static fields của class hay toàn bộ objects mà references trỏ tới. **Padding** xuất hiện vì field/object alignment. Các cải tiến như **compressed oops**, **compressed class pointers**, **Compact Object Headers** và field packing có thể thay đổi footprint rất nhiều khi có hàng triệu objects.

Để học/kiểm tra đúng, **luôn công bố giả định JVM 64-bit/32-bit, JDK version, header mode, compressed references và object alignment**, sau đó dùng **JOL** hoặc **Instrumentation.getObjectSize** trên runtime thực. Đừng biến một sơ đồ 12-byte header từ tài liệu HotSpot cũ thành quy luật của mọi phiên bản Java.

### Tài liệu tham khảo

- **OpenJDK Java Object Layout (JOL):** https://openjdk.org/projects/code-tools/jol/ và https://github.com/openjdk/jol — công cụ xem object header, field offsets, instance size và padding.
- **OpenJDK JEP 450 — Compact Object Headers (Experimental):** https://openjdk.org/jeps/450 — JDK 24.
- **OpenJDK JEP 519 — Compact Object Headers:** https://openjdk.org/jeps/519 — JDK 25.
- **Oracle JDK 17 — java command options:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html — các HotSpot flags `ObjectAlignmentInBytes`, `UseCompressedOops` và công cụ logging.
- **Java SE 17 `Instrumentation.getObjectSize`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object) — hợp đồng size estimate, không phải deep size.
- **HotSpot source (implementation):** https://github.com/openjdk/jdk/tree/master/src/hotspot/share/oops/ — các cấu trúc object headers, mark word và metadata. Chi tiết tại `master` có thể khác JDK 17; khi cần kiểm tra chính xác phải xem đúng branch/release.

**Thông điệp chính:** Java object có **overhead của JVM**, và số byte thật sự chiếm trong heap không được quyết định chỉ bởi danh sách fields trong `.java`. Nắm đúng **header — fields — alignment — padding**, rồi đo trên đúng HotSpot, sẽ giúp bạn hiểu footprint, tối ưu data structures và tránh suy đoán sai khi debug heap memory.