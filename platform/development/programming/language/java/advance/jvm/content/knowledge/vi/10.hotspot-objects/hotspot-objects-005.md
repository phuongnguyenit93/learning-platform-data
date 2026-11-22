# Compressed oops và compressed class pointers trong JVM 64-bit

## 1. Mục tiêu

Trên một máy 64-bit, địa chỉ native thường có độ rộng 64 bit. Nếu mọi trường tham chiếu Java trong object và mọi phần tử **Object[]** đều phải chiếm 8 byte, các ứng dụng có nhiều object sẽ tốn đáng kể bộ nhớ cho các reference. **HotSpot** có cơ chế **compressed ordinary object pointers (compressed oops)** để lưu nhiều tham chiếu đến Java heap objects bằng dạng mã hóa hẹp thường là **32 bit**. Một cơ chế khác, **compressed class pointers**, dùng dạng hẹp để biểu diễn **con trỏ tới thông tin loại đối tượng** trong object header.

Hai cơ chế giải quyết **hai loại con trỏ khác nhau**, tuy liên quan đến hiệu suất, kích thước object và cách HotSpot cấp phát vùng nhớ. Chúng không thay đổi kiểu tham chiếu trong Java source, không làm JVM từ 64-bit trở thành 32-bit, và không được quy định bắt buộc trong Java Virtual Machine Specification (JVMS).

Sau bài học, bạn có thể:

- Phân biệt **oop**, **narrowOop**, **Klass***, **narrowKlass** và **java.lang.Class**.
- Giải thích vì sao 32-bit encoded reference vẫn định vị được heap có dung lượng xấp xỉ hàng chục GiB nhờ **alignment**, **base** và **shift**.
- Đọc sơ đồ object header HotSpot 64-bit theo cấu hình **class pointers** được nén hoặc không nén.
- Tính kích thước giả định của một object hoặc reference array trong các cấu hình nén/không nén, có xét **padding**.
- Phân biệt ngưỡng **32 GiB thường được nhắc đến** với giới hạn tuyệt đối; hiểu tác động của **ObjectAlignmentInBytes** và heap placement.
- Biết các cờ **UseCompressedOops**, **UseCompressedClassPointers**, **ObjectAlignmentInBytes**, **CompressedClassSpaceSize**, và cách kiểm tra flag value thực chạy.
- Biết lợi ích, chi phí encode/decode, tác động tới cache locality, GC và khi nào benchmark thực tế mới đủ để kết luận.
- Dùng công cụ **jcmd**, **PrintFlagsFinal**, **JOL** và Java 17+ để quan sát mà không suy diễn sai từ số liệu.

**Phạm vi:** những layout minh họa dùng HotSpot 64-bit **Java 17**, với **object headers truyền thống** và alignment 8 byte, trừ khi ghi rõ khác. Các JVM implementations hoặc các JDK phiên bản khác có thể dùng tổ chức khác. Đây là cơ chế **HotSpot implementation**, không phải nghĩa vụ của mọi JVM tuân thủ Java SE.

## 2. Thuật ngữ: oop khác Klass pointer

Trong tài liệu và mã nguồn HotSpot:

- **oop** là một tham chiếu native-level tới **Java heap object**. Tên gọi lịch sử là *ordinary object pointer*.
- **narrowOop** là dạng encoded hẹp của một oop, thường 32 bit khi compressed oops bật.
- **Klass*** là con trỏ native-level tới cấu trúc metadata HotSpot mô tả **runtime class** của object.
- **narrowKlass** là dạng mã hóa hẹp của con trỏ **Klass***, thường dùng trong **object header** khi compressed class pointers bật.
- **java.lang.Class** là một **Java heap object** (class mirror) có thể quan sát từ Java bằng **SomeType.class**; nó **không phải** đối tượng cùng loại với cấu trúc native **Klass***.

Bảng so sánh:

| Khái niệm | Nó trỏ tới | Vị trí sử dụng tiêu biểu | Có đồng nghĩa Java reference không? |
| --- | --- | --- | --- |
| **oop** | Object/array trên Java heap | Object field, array element, nhiều đường xử lý VM | Là cách HotSpot biểu diễn reference tới Java object |
| **narrowOop** | Object/array trên Java heap sau giải mã | Object field/array element khi nén | Là encoding của oop |
| **Klass*** | Class metadata trong VM | Object header/VM internals | **Không** phải Java object reference thông thường |
| **narrowKlass** | Class metadata qua decoding | Object header khi nén class pointer | **Không** phải narrowOop |
| **Class<?> mirror** | Java object biểu diễn class | Reflection: **String.class**, **getClass()** | Là Java object, được tham chiếu bằng oop như object khác |

**Lỗi nghiêm trọng:** “Compressed class pointer là một compressed oop trỏ tới java.lang.Class object”. Không đúng. Object header chứa class/klass metadata pointer; Java Class mirror là đối tượng heap liên kết với metadata nhưng hai thứ không đồng nhất.

### 2.1. Hai luồng tham chiếu trong cùng một object

~~~text
Java:
class Container {
    Object item;
}

Một Container instance trên HotSpot (minh họa):
+------------------------------------------------+
| Mark word                                      |
| Encoded class pointer (narrowKlass) ----------+ |----> Klass metadata của Container
| Field item (narrowOop) -----------------------|----> Java heap object được item tham chiếu
| Padding nếu cần                               |
+------------------------------------------------+

Container.class ------> java.lang.Class mirror trên heap
                            |
                            +-- runtime liên kết với Klass metadata
~~~

Một field **item** có thể là **null** hoặc tham chiếu Object bất kỳ; class pointer trong object header biểu thị runtime type của chính **Container object**. Chúng không cùng nhiệm vụ, không dùng cùng address base và không thể hoán đổi.

## 3. Vì sao 64-bit VM cần tham chiếu nén?

Giả sử chương trình có một object chứa bốn reference fields và hàng triệu object tương tự. Nếu một reference chiếm 8 byte thay vì 4 byte, riêng bốn fields có thể tăng thêm **16 byte trên mỗi object trước khi xét alignment**. Ở một triệu objects, chênh lệch raw field storage đã là khoảng 16 triệu byte; tác động thực tế còn phụ thuộc object headers, padding và graph layout.

Đối với **Object[]**, mỗi phần tử là một reference slot, nên một mảng nhiều phần tử có thể hưởng lợi rõ:

~~~text
Reference slots của Object[8]:

Không nén:
  [8B][8B][8B][8B][8B][8B][8B][8B] = 64 B

Compressed oops:
  [4B][4B][4B][4B][4B][4B][4B][4B] = 32 B

Chưa bao gồm header, alignment hoặc đối tượng thực sự được tham chiếu.
~~~

Lợi ích không chỉ là **heap footprint**:

- Ít byte reference hơn có thể cải thiện **CPU cache locality**.
- Ít dữ liệu cần chuyển từ RAM/cache có thể giảm **memory bandwidth**.
- Một số bộ phận GC duyệt object graph có ít byte reference để đọc/ghi.
- Với workload chịu giới hạn bởi cache/memory, hiệu quả có thể tích cực.

Đổi lại, runtime phải **encode/decode** reference ở những vị trí thích hợp. JIT compiler có thể tối ưu hoặc gộp thao tác; do đó không thể tuyên bố luôn nhanh hơn hoặc luôn chậm hơn nếu không benchmark. Tác động phụ thuộc heap size, object graph, CPU architecture, GC, compiler và cấu hình.

## 4. “32-bit reference mà vẫn trỏ được heap 32 GiB” nghĩa là gì?

Nếu 32 bit biểu diễn **byte address trực tiếp**, ta có tối đa:

~~~text
2^32 byte = 4 GiB
~~~

Nhưng một đối tượng thường được căn chỉnh ở địa chỉ chia hết cho **8 byte** trong HotSpot 64-bit cấu hình mặc định. Ba bit thấp của **offset** theo đơn vị byte luôn bằng 0. Thay vì lưu địa chỉ từng byte, VM có thể lưu **offset theo đơn vị 8 byte**.

Ý tưởng:

~~~text
Địa chỉ/offset thực:   0x00000000_00000018 = 24 byte
Mã hóa dạng đơn vị 8:  24 / 8 = 3

32-bit narrow value:  3
Decode (shift=3):     3 << 3 = 24
~~~

Với 2^32 khả năng mã hóa, mỗi bước biểu diễn 8 byte, phạm vi lý thuyết là:

~~~text
2^32 * 8 byte = 2^35 byte = 32 GiB
~~~

Đây là lý do nhiều tài liệu nói compressed oops hỗ trợ heap khoảng **32 GiB** với 8-byte alignment. **Không** phải mọi 32-bit narrow value trỏ tới một object hợp lệ hoặc mỗi object chỉ chiếm 8 byte; đây là phạm vi **địa chỉ hóa**, không phải số object thực.

### 4.1. Base + shift

Một sơ đồ giải mã phổ biến cho **non-null** narrow oop:

~~~text
decoded_address = base + (unsigned(narrowOop) << shift)
~~~

Trong đó:

- **base**: địa chỉ cơ sở (hoặc 0) theo encoding mode.
- **shift**: số bit dịch, thường là **3** với object alignment 8 byte.
- **narrowOop**: giá trị encoded 32-bit.
- **decoded_address**: địa chỉ native-level tương ứng được HotSpot dùng để tham chiếu object.

Chiều ngược (trong phạm vi các giá trị hợp lệ, alignment thích hợp):

~~~text
narrowOop = (decoded_address - base) >> shift
~~~

**Đây là mô hình hóa**, không phải API Java truy xuất con trỏ. Những chi tiết về NULL encoding, read/write barriers, GC forwarding và vùng địa chỉ đều do VM thực hiện.

### 4.2. Ví dụ số học với base khác 0

Giả sử *một mode* có:

~~~text
base          = 0x0000001000000000
shift         = 3
encoded value = 7
offset        = 7 * 8 = 56 decimal = 0x38

decoded address = 0x0000001000000038
~~~

Đây là **địa chỉ giả định**, không phải địa chỉ thật của một Java object trong chương trình. Nó cho thấy vì sao cả **base** và **shift** cùng cần thiết. Dạng zero-based có base bằng 0 nên phép cộng base có thể biến mất, giúp mã nhanh hơn trong một số tình huống.

### 4.3. Không quên null

Java reference có giá trị **null**. HotSpot bảo đảm encoded narrowOop giá trị 0 có thể được nhận diện như null theo quy tắc implementation. Với các heap-based modes, việc xử lý null có thể cần nhánh/special handling, không thể máy móc suy rằng mọi con trỏ có giá trị 0 decode thành **base** và được Java coi là một object hợp lệ.

Khi tự mô phỏng công thức bằng số nguyên, nhớ đây là minh họa cho **non-null aligned references**; null là trường hợp đặc biệt.

## 5. Các encoding modes của compressed oops

Tài liệu và mã nguồn HotSpot phân biệt những modes nhằm tối ưu phép giải mã tùy vị trí cấp phát Java heap:

| Mode (tên thường gặp) | Ý tưởng | Shift/base |
| --- | --- | --- |
| **Unscaled / 32-bit** | Heap nằm trong phạm vi địa chỉ nhỏ, encoded value có thể dùng trực tiếp như offset byte | Có thể shift=0, base=0 |
| **Zero-based** | Heap nằm trong vùng địa chỉ phù hợp cho base=0 | Thường shift=3 nếu cần địa chỉ hóa xa hơn 4 GiB |
| **Non-zero / heap-based** | Dùng base địa chỉ khác 0 và offset được scale | Base != 0, shift thường 3 |
| **Disjoint-base** (mode triển khai phù hợp) | Chọn base với bit pattern thuận lợi để tối ưu giải mã | Vẫn là encoded offset + base logic, có thể tối ưu bằng OR |

**Không thể ép mọi JVM/OS/JDK chỉ sử dụng đúng một mode.** VM phải có khả năng reserve heap ở vùng địa chỉ phù hợp; ASLR, address space layout, kích thước heap và tham số VM tác động tới mode được chọn.

Một dòng log HotSpot có thể diễn đạt kiểu:

~~~text
Compressed Oops mode: Zero based
Oop shift amount: 3
~~~

Đây là ví dụ hình thức log, **không phải stdout cố định** cho mọi lần chạy hoặc mọi JDK. Mọi con số về heap base/mode phải đo từ tiến trình thực.

### 5.1. 32 GiB không phải một vách giới hạn độc lập với mọi cờ

Câu “compressed oops chỉ hoạt động khi -Xmx dưới 32G” là đơn giản hóa quá mức:

- Với alignment 8 byte, **32 GiB** là phạm vi lý thuyết từ 32-bit values dịch 3 bit.
- Các chi tiết reservation/guard/alignment có thể khiến ngưỡng bật tắt thực tế thấp hơn con số đúng 32 GiB trên một JVM cụ thể.
- **-XX:ObjectAlignmentInBytes** có thể thay đổi độ căn chỉnh của object, khiến shift và miền địa chỉ hóa thay đổi.
- Ví dụ alignment **16** cho phạm vi lý thuyết **2^32 × 16 = 64 GiB**, nhưng chi phí padding/fragmentation cũng có thể tăng.
- VM có thể tự tắt compressed oops hoặc từ chối cấu hình nếu yêu cầu không thể hỗ trợ; không nên suy từ **-Xmx** đơn lẻ rằng cờ cuối cùng chắc chắn bật.

**Không coi tăng alignment là tối ưu mặc định.** Tăng object alignment khiến nhiều objects nhỏ tốn padding hơn; phần tham chiếu tiết kiệm được có thể bị lấn át. Chọn bằng phép đo thực tế và kiểm tra JVM flags cuối cùng.

## 6. Compressed class pointers dùng để làm gì?

Mỗi Java heap object trong HotSpot có **object header** chứa thông tin quản lý object và thông tin về **class metadata** của object. Trong header truyền thống 64-bit:

- **Mark word**: vùng thông tin runtime của object; ý nghĩa bit phụ thuộc trạng thái/phiên bản HotSpot (hash/locking/GC age...).
- **Klass pointer**: tham chiếu tới metadata mô tả runtime class của object.
- Với **array object**, còn có **array length** trong header truyền thống.

Khi **compressed class pointers** bật, thành phần class pointer trong header có thể được lưu dưới dạng **narrowKlass 4 byte** thay vì **Klass* 8 byte**.

**NarrowKlass khác narrowOop**:

| Câu hỏi | Compressed oops | Compressed class pointers |
| --- | --- | --- |
| Đang nén thứ gì? | Tham chiếu tới **Java heap objects** | Tham chiếu tới **Klass metadata** |
| Xuất hiện ở đâu? | Java reference fields, arrays và vị trí thích hợp khác | Object header class pointer |
| Miền địa chỉ đích? | Java heap | Vùng class metadata/class space |
| Encoding base/shift? | Gắn với object heap | Gắn với địa chỉ class metadata, có quy tắc riêng |
| Ảnh hưởng trực tiếp? | Kích thước reference field/array element | Kích thước class-pointer component trong header |
| Cờ HotSpot liên quan? | **UseCompressedOops** | **UseCompressedClassPointers** |

Với class pointer compression, VM có thể dành một vùng địa chỉ phục vụ class metadata để narrowKlass có thể encode/decode phù hợp. **CompressedClassSpaceSize** là một tùy chọn liên quan, nhưng không phải heap-size limit và không đồng nghĩa toàn bộ Metaspace capacity.

### 6.1. Klass*, Class mirror và class loader

~~~text
Java heap:
   anObject ----> Object header ----> Klass* metadata
   SomeType.class ----> java.lang.Class mirror object

Native class metadata:
   Klass structure mô tả SomeType
     - class loader identity
     - fields/methods/runtime metadata...
~~~

Quan hệ giữa Java mirror và VM metadata do HotSpot quản lý. Khi đọc:

~~~java
Class<?> type = anObject.getClass();
~~~

Java code nhận **Class mirror**. Điều này **không** có nghĩa VM chỉ lấy chính giá trị narrowKlass 32-bit rồi trả nó như một Java reference nguyên xi. Runtime phải cung cấp đúng Java object reference tới mirror theo cơ chế nội bộ.

**Cùng binary name ở hai defining class loaders** có thể tạo hai runtime classes và hai Klass metadata khác nhau. Vì vậy class pointer của instances tương ứng phải trỏ tới đúng metadata của runtime class đó.

## 7. Object header và kích thước trên HotSpot 64-bit truyền thống

Bảng sau giả định layout **HotSpot 64-bit Java 17**, object headers truyền thống, object alignment 8 byte, không có biến thể header khác. Những số này là **ví dụ điển hình**, không phải quy định của JVMS và không cam kết giống nhau trên mọi runtime.

| Header của object thường | Có compressed class pointer | Không compressed class pointer |
| --- | ---: | ---: |
| Mark word | 8 B | 8 B |
| Klass pointer | 4 B | 8 B |
| Tổng header **trước padding** | **12 B** | **16 B** |

Với mảng trong layout truyền thống, phần **array length** thường thêm **4 B**:

| Header của array | Có compressed class pointer | Không compressed class pointer |
| --- | ---: | ---: |
| Mark word | 8 B | 8 B |
| Klass pointer | 4 B | 8 B |
| Array length | 4 B | 4 B |
| Raw header bytes | 16 B | 20 B |
| Vị trí phần tử đầu tiên | Theo căn chỉnh phần tử và layout, thường 16 B cho Object[] compressed | Có thể cần padding để vị trí phần tử tham chiếu phù hợp |

**Chú ý:** compressed oops quyết định độ rộng element references; compressed class pointer quyết định độ rộng header pointer. Vì vậy **phải xét hai cờ**, không thể chỉ nói “bật compressed oops thì mọi header là 12 byte” trong mọi cấu hình.

### 7.1. Ví dụ layout của Holder có ba references

~~~java
// Mã minh họa về layout, không phải yêu cầu thuộc tính bộ nhớ của Java:
final class Holder {
    Object first;
    Object second;
    Object third;
}
~~~

Giả sử HotSpot 64-bit traditional headers, object alignment 8 byte.

**Cả compressed oops và compressed class pointers đều bật**:

~~~text
Offset  Bytes   Thành phần
0       8       Mark word
8       4       narrowKlass
12      4       narrowOop first
16      4       narrowOop second
20      4       narrowOop third
------------------------------
Total raw          24 bytes
Rounded to 8       24 bytes
~~~

**Cả hai đều tắt** (wide object references và wide klass pointer):

~~~text
Offset  Bytes   Thành phần
0       8       Mark word
8       8       Klass*
16      8       oop first
24      8       oop second
32      8       oop third
------------------------------
Total raw          40 bytes
Rounded to 8       40 bytes
~~~

Chênh lệch minh họa là **40 - 24 = 16 byte/object**, tức 40% của kích thước wide. Một triệu Holder instances về mặt **shallow instance size lý tưởng** có chênh lệch 16 triệu byte trước khi xét GC overhead, allocation metadata khác và những objects được tham chiếu.

**Không tuyên bố “một object Java luôn có header 12 byte”**: ngoài class pointer width còn có JDK/VM mode, array kind, header implementation, alignment và các quyết định cấp phát.

### 7.2. Ví dụ object có hai int fields: padding có thể triệt tiêu tiết kiệm

~~~java
final class Point {
    int x;
    int y;
}
~~~

Với cùng giả định HotSpot 64-bit:

~~~text
Compressed klass:
  header 12 + x 4 + y 4 = 20 -> align8 = 24 B

Wide klass:
  header 16 + x 4 + y 4 = 24 -> align8 = 24 B
~~~

Cả hai đều 24 byte do alignment. Điều đó cho thấy **4 byte giảm ở header không chắc chắn giảm shallow size cuối cùng của mọi loại object**; padding có thể hấp thụ phần tiết kiệm.

### 7.3. Ví dụ Object[1000]

Giả sử array header compressed klass dài 16 byte, compressed oop element 4 byte, 8-byte alignment:

~~~text
Object[1000] compressed:
  16 + 1000 * 4 = 4016 B
  align8 => 4016 B
~~~

Với wide klass và wide element references, header phần tử có thể bắt đầu ở offset 24:

~~~text
Object[1000] wide:
  24 + 1000 * 8 = 8024 B
  align8 => 8024 B
~~~

Chênh lệch shallow size minh họa là **4008 byte** cho array này, **không** tính 1000 objects mà các phần tử có thể trỏ tới. Nếu array chỉ chứa null, bản thân backing array vẫn có các slots; việc không có object được tham chiếu không xóa bộ nhớ của slots.

### 7.4. Primitive arrays và fields

**int[]**, **byte[]**, **long[]** chứa primitive elements, không chứa Java object references ở từng phần tử. Vì vậy **compressed oops không tự làm phần tử int từ 4 byte thành 2 byte** hoặc phần tử long từ 8 thành 4.

Class pointer compression vẫn có thể ảnh hưởng **header của primitive array**, nhưng element widths là chuyện khác.

| Thành phần | Bị đổi độ rộng trực tiếp bởi compressed oops? |
| --- | --- |
| Object reference field | Có trong layout HotSpot phù hợp |
| Object[] element reference | Có |
| int/float field | Không |
| long/double field | Không |
| byte/char/boolean primitives | Không trực tiếp bởi oop compression |
| Klass pointer trong header | Thuộc compressed **class pointers**, không phải oop fields |
| Đối tượng Java mà reference trỏ tới | Vẫn là object, kích thước riêng |

## 8. Vì sao hai cơ chế đều liên quan nhưng không phải một?

Nhiều HotSpot configurations mặc định bật cả hai cơ chế. Tuy vậy cần phân biệt:

- **UseCompressedOops** điều khiển representation của các oop locations thích hợp.
- **UseCompressedClassPointers** điều khiển representation của klass references trong object headers theo khả năng HotSpot.
- Tập điều kiện/chính sách bật từng flag có thể khác theo JDK version, kiến trúc và quan hệ giữa các flags.
- Không suy từ **UseCompressedOops=true** mà **không kiểm tra** thì mọi môi trường đều chắc **UseCompressedClassPointers=true**.
- Không suy từ “class metadata được nén” rằng toàn bộ **Metaspace** hoặc mọi pointer trong JVM đều giảm nửa.

Trong JDK 17/HotSpot, compressed class pointers gắn với một vùng **compressed class space** được quản lý cùng cơ chế Metaspace phù hợp. Theo tài liệu tuning Oracle Java 17, **CompressedClassSpaceSize** có default được nêu là **1 GiB** trong cấu hình tương ứng; giá trị cờ thực tế có thể khác do version/ergonomics/explicit overrides.

**Compressed class space không phải Java heap.** Không tăng **-Xmx** để “mở thêm chỗ cho narrowKlass metadata” theo kiểu suy luận trực tiếp; cần xem class metadata counts, Metaspace/CCS flags và native memory budget.

## 9. Phép giải mã reference có làm Java code khác đi không?

Không. Theo ngôn ngữ Java, những biểu thức:

~~~java
Object a = new Object();
Object b = a;
Object c = new Object();
System.out.println(a == b);
System.out.println(a == c);
~~~

có ý nghĩa **identity comparison** của Java objects, độc lập việc VM lưu oop ở dạng wide hay compressed. Việc VM phải decode narrowOop trước khi sử dụng một object không làm **==** thành so sánh chuỗi bytes encoded theo một contract công khai.

Những thứ Java code **không** được suy ra:

- Pointer address thực từ **System.identityHashCode**.
- Kích thước reference slot từ **Class.getName()**.
- Memory address của Object qua **Object.toString()**.
- NarrowOop payload từ **equals** hoặc một phép cast.
- Object được xếp liên tục, không di chuyển bởi GC.

Java reference là kiểu giá trị trừu tượng; HotSpot có thể nén, giải nén, giữ giá trị trong thanh ghi, và GC có thể di chuyển objects, miễn ngữ nghĩa Java được giữ nguyên.

## 10. Ví dụ Java 17+ số 1: reference semantics bất biến theo cờ nén

Tạo file **ReferenceSemanticsDemo.java**:

~~~java
public class ReferenceSemanticsDemo {
    static final class Node {
        Node next;
        int value;

        Node(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Node a = new Node(7);
        Node same = a;
        Node other = new Node(7);
        a.next = other;

        Node[] nodes = {a, same, other};

        System.out.println("sameRef=" + (a == same));
        System.out.println("differentObject=" + (a != other));
        System.out.println("sameValue=" + (a.value == other.value));
        System.out.println("arrayAlias=" + (nodes[0] == nodes[1]));
        System.out.println("link=" + (a.next == nodes[2]));
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ReferenceSemanticsDemo.java
java ReferenceSemanticsDemo
~~~

**Stdout:**

~~~text
sameRef=true
differentObject=true
sameValue=true
arrayAlias=true
link=true
~~~

Chạy thêm trên một **HotSpot 64-bit** hỗ trợ cờ sau:

~~~bash
java -XX:-UseCompressedOops ReferenceSemanticsDemo
~~~

**Stdout Java-level vẫn như trên**, vì compressed oop chỉ là representation nội bộ. Nhưng shallow size của objects/arrays có thể đổi. Không coi việc stdout giống nhau là bằng chứng **cờ đã được bật/tắt đúng ý**: phải đọc các final flag values theo mục tiếp theo.

### 10.1. Điều không thể đo bằng ví dụ này

Ví dụ trên **không** hiển thị addresses, header bits hay số byte của reference. Nó chỉ xác nhận semantics của Java được giữ. Muốn xem layout HotSpot thực, dùng JOL/diagnostic VM tools. Không nên cố viết Java source đọc private native pointers hoặc dùng unsafe memory hacks trong bài tập nền tảng.

## 11. Ví dụ Java 17+ số 2: tính toán layout minh họa (không phải introspection)

Tạo file **LayoutArithmeticDemo.java**:

~~~java
public class LayoutArithmeticDemo {
    static int alignUp(int bytes, int alignment) {
        return ((bytes + alignment - 1) / alignment) * alignment;
    }

    static int holderSize(int headerBytes, int referenceBytes,
                          int references, int alignment) {
        return alignUp(headerBytes + referenceBytes * references, alignment);
    }

    static int arraySize(int headerBytes, int elementBytes,
                         int length, int alignment) {
        return alignUp(headerBytes + elementBytes * length, alignment);
    }

    public static void main(String[] args) {
        int compressedHolder = holderSize(12, 4, 3, 8);
        int wideHolder = holderSize(16, 8, 3, 8);
        int compressedArray = arraySize(16, 4, 1000, 8);
        int wideArray = arraySize(24, 8, 1000, 8);

        System.out.println("holderCompressed=" + compressedHolder);
        System.out.println("holderWide=" + wideHolder);
        System.out.println("arrayCompressed=" + compressedArray);
        System.out.println("arrayWide=" + wideArray);
        System.out.println("holderSavings=" + (wideHolder - compressedHolder));
        System.out.println("arraySavings=" + (wideArray - compressedArray));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 LayoutArithmeticDemo.java
java LayoutArithmeticDemo
~~~

**Stdout chính xác:**

~~~text
holderCompressed=24
holderWide=40
arrayCompressed=4016
arrayWide=8024
holderSavings=16
arraySavings=4008
~~~

Chương trình dùng **tham số layout giả định** của cấu hình HotSpot truyền thống. Nó không truy cập memory layout của VM đang chạy và sẽ in cùng số ngay cả khi bạn tắt compressed oops. Phần quan trọng là hiểu **tính toán + alignment**, không nhầm kết quả số học này với công cụ đo heap.

### 11.1. Hạn chế của công thức

**alignUp(raw, 8)** chỉ mô phỏng rounding ở cấp object size. HotSpot có thể sắp xếp lại fields, chèn padding nội bộ và bố trí header/array theo cấu hình runtime. Với class có mixed-width fields và inheritance, công thức lấy header cộng sum(field sizes) có thể không phản ánh chính xác layout. Cần đo class cụ thể.

## 12. Cách kiểm tra cờ JVM đang bật thật

Trên **HotSpot/OpenJDK/Oracle JDK 17 64-bit**, dùng các lệnh:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Dòng output có thể gồm các flags:

~~~text
UseCompressedOops
UseCompressedClassPointers
ObjectAlignmentInBytes
CompressedClassSpaceSize
MaxHeapSize
MaxMetaspaceSize
~~~

Thực tế, **PrintFlagsFinal in rất nhiều flags**; tìm các tên trên bằng công cụ search của terminal. Không khẳng định một thứ tự dòng hay giá trị bool cố định, vì ergonomic flags có thể phụ thuộc phiên bản, bộ nhớ máy, container và các options khác.

Trên Linux/macOS có thể lọc:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes|CompressedClassSpaceSize|MaxHeapSize'
~~~

Trong PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
  Select-String 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes|CompressedClassSpaceSize|MaxHeapSize'
~~~

**Chỉ so sánh giá trị cùng điều kiện startup.** Nếu ứng dụng production chạy trong container dùng thêm memory limits, các cờ do ergonomics chọn có thể khác một lệnh java trần trên laptop.

### 12.1. Bật/tắt nén trong thí nghiệm

Ví dụ (chỉ với HotSpot implementation hỗ trợ):

~~~bash
java -Xmx512m -XX:+UseCompressedOops ReferenceSemanticsDemo
java -Xmx512m -XX:-UseCompressedOops ReferenceSemanticsDemo
~~~

Dùng **PrintFlagsFinal** với cùng flags để xác nhận final state:

~~~bash
java -Xmx512m -XX:-UseCompressedOops -XX:+PrintFlagsFinal -version
~~~

Không tự động cố bật một cờ không được cấu hình/JVM hỗ trợ trong production. Một số flags có dependencies, cần VM quyết định giá trị khả thi; kết quả quyết định cuối cùng phải kiểm tra trong output.

**Đừng nhầm:** **-Xmx512m** là max heap size; nó không trực tiếp giới hạn số byte của **class metadata**, không cho biết used heap, và không nói memory đang được process commit thật sự là 512 MiB.

### 12.2. Quan sát compression mode và GC logs

HotSpot có các logging tags cho compressed oops/heap ở một số versions/configurations. Ví dụ định hướng:

~~~bash
java -Xlog:gc+heap+coops=debug -version
~~~

Không mọi build/mode đều in cùng dữ liệu. Dùng:

~~~bash
java -Xlog:help
~~~

để xem tags hợp lệ trên JVM đang chạy. Khi có log, bạn có thể tìm **Compressed Oops mode**, heap address range hoặc oop shift; đây là diagnostic output, **không phải API ổn định**.

### 12.3. jcmd cho tiến trình thật

Nếu dùng HotSpot và JDK tools:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.flags
jcmd <PID> VM.metaspace
~~~

Thay **<PID>** bằng PID thực. Một số commands/cấp độ chi tiết phụ thuộc JDK build và quyền truy cập; luôn đọc **jcmd <PID> help** trước khi áp dụng. **VM.metaspace** giúp điều tra class metadata, không xuất chính xác kích thước từng oop field của mỗi object.

## 13. Dùng Java Object Layout (JOL) để quan sát object thực

**JOL (Java Object Layout)** là công cụ của OpenJDK để khám phá/ước lượng memory layout JVM. Nó có thể hiển thị kích thước field references, offset, header, alignment và sự khác biệt giữa cấu hình VM.

Ví dụ thao tác khi đã có đúng JOL CLI JAR:

~~~bash
java -jar jol-cli.jar internals java.lang.Integer
~~~

Hoặc dùng JOL **jol-core** qua dependency phù hợp và API **ClassLayout** trong một dự án Java. Đây là ví dụ command phụ thuộc JAR được cung cấp từ OpenJDK JOL, **không phải lệnh Java 17 mặc định**; nếu chưa tải JOL, chương trình không chạy chỉ với JDK.

Tại output JOL truyền thống có thể thấy:

~~~text
(object header: mark)       8 bytes
(object header: class)      4 bytes nếu narrowKlass
field Integer.value         4 bytes
Instance size               16 bytes với cấu hình minh họa
~~~

Ví dụ này là dữ liệu **có điều kiện** (HotSpot 64-bit, compressed class pointers và alignment tương ứng). Khi thay JVM flags, field layout và padding có thể khác.

**Ưu tiên đo bằng JOL**, thay vì dùng **System.getProperty("sun.arch.data.model")** rồi suy ra reference width: 64-bit process không đồng nghĩa mọi object reference field 8 byte.

### 13.1. So sánh thí nghiệm công bằng

Để kiểm tra tác động nén trên memory footprint:

1. Dùng cùng **JDK build**, cùng GC và cùng dataset.
2. Bật nén rồi tắt nén ở các JVM processes riêng biệt.
3. Kiểm tra flags **UseCompressedOops** và **UseCompressedClassPointers** cuối cùng.
4. Giữ **-Xms/-Xmx**, ObjectAlignmentInBytes và những tham số liên quan ở mức kiểm soát được.
5. Dùng JOL đo shallow size object/array cụ thể.
6. Dùng heap histogram/profiler đo retained graph sizes nếu cần.
7. Benchmark có warm-up và measurement đúng phương pháp để xem throughput/latency, không suy từ một lần chạy nhỏ.
8. Xem GC allocation rates/pauses và RSS/native memory budget nếu mục tiêu là memory.

**Giá trị đo nào đang so?** Shallow size khác retained size; allocated bytes khác live heap; reserved memory khác committed memory, khác RSS. Nén references tác động rõ đến một số loại storage, không đồng nhất các con số đo này.

## 14. Tác động đối với GC, CPU cache và JIT

### 14.1. CPU cache và băng thông

Một object graph nặng về pointers thường được duyệt bằng thao tác dereference. Với 4-byte narrowOop thay cho 8-byte wide oop, các phần chứa references có thể nhỏ hơn:

- Cache line chứa được nhiều slots hơn.
- Nhiều phần của graph nằm vừa L1/L2/L3 hơn.
- VM/GC cần đọc/ghi ít byte reference hơn trong một số pha.

Nhưng mỗi lần dereference có thể cần tính **base + shift**, và JIT compiler/CPU architecture có thể áp dụng tối ưu addressing để giảm chi phí. Vì vậy **nén references không đồng nghĩa tốc độ tăng đúng 2×** hoặc mọi lookup không có overhead.

### 14.2. GC barriers và object movement

GC có thể di chuyển Java objects; references cần được cập nhật/diễn giải theo đúng encoding. Một số collectors có read/write barriers hoặc load barriers khác nhau, ảnh hưởng đường thực thi nhưng vẫn bảo toàn semantics.

Đừng tự xem compressed oop như **số nguyên 32 bit bất biến về địa chỉ object** khi GC chuyển object. Representation và update logic là trách nhiệm runtime. Công thức encode/decode chỉ giúp hiểu miền địa chỉ hóa, không phải lời mời sửa object references ở cấp Java source.

### 14.3. JIT có thể thay đổi cách cất reference

Không phải mọi Java reference liên tục nằm trong một 4-byte memory slot. JIT có thể giữ reference trong CPU register, unbox/scalar-replace/loại bỏ object allocation theo điều kiện escape analysis, hoặc dùng các intermediate formats. Cơ chế compressed oops áp dụng ở **những oop locations phù hợp trong HotSpot implementation**, không là quy tắc “mọi biến reference trong mọi thời điểm chiếm đúng 4 byte”.

## 15. Khi nào nén không tiết kiệm như kỳ vọng?

1. **Object quá ít reference fields:** Phần tiết kiệm thấp; header reduction có thể bị alignment padding hấp thụ.
2. **Object nhỏ nhưng alignment tăng:** Nếu tăng ObjectAlignmentInBytes lên 16/32 để hỗ trợ phạm vi lớn hơn, padding trung bình có thể tăng.
3. **Application memory chủ yếu là primitive arrays:** Giảm width của oop slots ít tác động trực tiếp tới phần tử primitives.
4. **Ứng dụng giữ nhiều byte[]/char[]:** Nội dung buffer là bytes/chars, không phải object-reference slots.
5. **Bộ nhớ native/direct buffers lớn:** Compressed oops ảnh hưởng Java object refs, không tự giảm vùng **DirectByteBuffer native memory**, thread stacks hoặc code cache.
6. **Heap có ít live objects:** Thay đổi reserved capacity không có nghĩa footprint thực của graph lớn.
7. **Object sharing và dedup:** Tỷ lệ objects và references thực tế quan trọng hơn chỉ số lượng class declarations.
8. **Code nặng CPU arithmetic:** Cache benefit có thể nhỏ, encode/decode cost tùy VM/JIT.
9. **Heap requirement vượt miền compression thuận lợi:** VM có thể chọn wide oops hoặc cần cấu hình alignment khác, gây trade-off mới.
10. **Compressed class space trở thành bottleneck:** Đó là câu chuyện class metadata capacity/unloading, không tự giải bằng giảm Java oop field width.

## 16. Phân biệt ba ngưỡng bộ nhớ hay bị trộn

| Ngưỡng | Nó giới hạn gì? | Ví dụ/cờ liên quan |
| --- | --- | --- |
| **Khoảng 32 GiB với shift=3** | Phạm vi địa chỉ hóa lý thuyết của narrowOop với 8-byte scale | UseCompressedOops, ObjectAlignmentInBytes |
| **Java heap maximum** | Mức max heap JVM được cấu hình/ergonomics chọn | -Xmx, MaxHeapSize |
| **Compressed class space** | Vùng quản lý class metadata cần cho narrowKlass encoding | UseCompressedClassPointers, CompressedClassSpaceSize |

Một chương trình có Java heap 8 GiB không cần 8 GiB compressed class space. Một chương trình có hàng trăm nghìn generated classes có thể chịu áp lực metadata ngay khi live object heap rất nhỏ.

### 16.1. CompressedClassSpaceSize không phải giới hạn mọi metadata

HotSpot Metaspace có nhiều cấu trúc/kiểu cấp phát. Phần **compressed class space** chỉ là một phần liên quan đến narrowKlass. Tăng hoặc giảm **CompressedClassSpaceSize** không đồng nghĩa toàn bộ **Metaspace** được tăng/giảm đúng lượng đó.

Khi thấy **OutOfMemoryError: Compressed class space** hoặc **OutOfMemoryError: Metaspace**, hãy xem class loading growth, class-loader retention, GC class unloading và flags; tránh chỉ đổi -Xmx rồi kết luận đã điều chỉnh đúng.

## 17. Phân biệt điểm “oop” trong JVM và ordinary Java object

HotSpot dùng thuật ngữ **oop** cho cách diễn đạt nội bộ về Java heap references. Đây không phải từ khóa của Java source:

~~~java
Object ref = new Object();
~~~

Biến **ref** có kiểu Java reference; compiler/JVM quản lý representation. Trong class file **aload/astore/getfield/putfield/aaload/aastore** hoạt động trên các loại JVM values/references theo JVMS. Bytecode không chứa một loại field descriptor riêng có tên **narrowOop**.

**Không có descriptor nén tham chiếu:** Field kiểu **Object** vẫn có descriptor **Ljava/lang/Object;**, mảng Object[] vẫn **[Ljava/lang/Object;** bất kể -XX:+/-UseCompressedOops.

Tương tự, **Klass*** và **narrowKlass** không phải Java source types, không thể import như class API Java thông thường, không hiển thị trong **javap -s** như field declared by user.

### 17.1. Class.getClassLoader() và class pointer

Một class được định danh runtime bằng tên nhị phân và defining loader. Khi object header mang Klass metadata pointer, metadata đó liên quan đúng runtime class. Nhưng từ Java chỉ có thể quan sát an toàn qua:

~~~java
Class<?> type = object.getClass();
ClassLoader loader = type.getClassLoader();
~~~

Đây là Java-level Reflection. Không dùng output **getClassLoader().toString()** như địa chỉ native của Klass; cũng không suy rằng **Class object** và **Klass metadata** là cùng object trên heap.

## 18. Những hiểu lầm phổ biến

1. **“JVM 64-bit bắt buộc mọi Java reference chiếm 8 byte.”** Sai trong HotSpot có compressed oops.
2. **“Compressed oops làm object address chỉ có 32 bit.”** Sai: 32-bit **encoded value** giải mã ra native address có thể rộng hơn.
3. **“2^32 × 8 byte là đúng 32 GB trong mọi tình huống.”** Chỉ là miền địa chỉ hóa lý thuyết của 8-byte scale; heap placement/flags/guard có ràng buộc thực.
4. **“UseCompressedOops và UseCompressedClassPointers là cùng một flag.”** Sai: hai loại pointer khác nhau.
5. **“Class pointer là reference tới java.lang.Class Java object.”** Sai: trỏ tới Klass metadata.
6. **“NarrowOop và narrowKlass dùng cùng base/shift.”** Sai: hai miền địa chỉ đích và encoding settings khác nhau.
7. **“Mọi heap objects nhỏ đi đúng 4 byte khi nén class pointer.”** Sai: alignment padding có thể khiến shallow size không đổi.
8. **“Tất cả Java objects có header 12 byte.”** Sai: phụ thuộc mode, JDK, đối tượng thường/mảng và implementation.
9. **“Object[1000] chỉ tốn 4000 byte khi nén.”** Sai: còn array header và alignment.
10. **“int[] được nén mỗi int xuống 2 byte.”** Sai: primitive element widths không do UseCompressedOops quyết định.
11. **“String.intern pool chính là vùng compressed class pointers.”** Sai: hai cơ chế không liên quan như vậy.
12. **“Chỉ tăng -Xmx là tăng compressed class space.”** Sai: hai vùng/cờ thuộc các tài nguyên khác nhau.
13. **“JOL mô tả chuẩn layout mọi JVM.”** Sai: JOL đo/ước lượng theo VM, không thay JVMS.
14. **“Tắt compressed oops luôn tăng hiệu năng vì bỏ shift.”** Sai: cache/memory costs có thể lớn hơn decode cost.
15. **“Bật compressed oops luôn giảm một nửa heap.”** Sai: hiệu quả tùy tỷ trọng references, header, padding, primitive data và GC.
16. **“Một object Java không thể bị GC di chuyển vì có encoded address.”** Sai: HotSpot/GC duy trì references khi cần.
17. **“Có thể đọc compressed oop bằng System.identityHashCode.”** Sai: hash không phải memory address.
18. **“Class files có descriptor narrowOop.”** Sai: compression là runtime implementation detail.
19. **“32 GiB là ngưỡng tuyệt đối không thể vượt với compression.”** Sai: object alignment có thể thay đổi miền, đi kèm trade-offs.
20. **“HotSpot Metaspace và Java heap cùng được kiểm soát bởi -Xmx.”** Sai: native metadata cần xem giới hạn riêng.

## 19. Bài tập có đáp án

**Bài 1.** Trên 64-bit HotSpot, nếu một Object reference field lưu bằng narrowOop 4 byte, VM có còn dùng native 64-bit addresses không?

**Đáp án:** Có. Encoded narrowOop là representation hẹp; VM có thể decode thành địa chỉ native đầy đủ khi sử dụng.

**Bài 2.** Với alignment 8 byte, shift thường là bao nhiêu và phạm vi địa chỉ hóa lý thuyết bằng bao nhiêu?

**Đáp án:** Shift 3, vì 2^3=8. Miền 2^32×8 = 2^35 bytes, tức 32 GiB.

**Bài 3.** Tại sao tăng ObjectAlignmentInBytes=16 có thể cho miền 64 GiB trong công thức nhưng lại lãng phí bộ nhớ?

**Đáp án:** Shift 4 tương ứng 16-byte scale; mọi object phải được căn chỉnh theo bước lớn hơn nên padding/fragmentation có thể tăng.

**Bài 4.** Khác biệt giữa narrowOop và narrowKlass?

**Đáp án:** NarrowOop mã hóa reference tới Java heap object; narrowKlass mã hóa con trỏ tới class metadata của object.

**Bài 5.** Trong header truyền thống với 8-byte mark word, compressed klass pointer 4 byte, raw object header là bao nhiêu?

**Đáp án:** 12 byte trước padding cho object thường trong cấu hình giả định.

**Bài 6.** Vì sao Object[1000] không chỉ có 1000×4=4000 byte với compressed oops?

**Đáp án:** Còn array header và alignment; ví dụ compressed klass+oop, alignment8, array header16 → 4016 bytes.

**Bài 7.** Một class Point chỉ có hai int fields. Vì sao có thể 24 bytes trong cả wide và compressed klass modes?

**Đáp án:** Header compressed12+8 primitive=20, round lên 24; header wide16+8=24. Padding triệt tiêu khác biệt.

**Bài 8.** Khi đọc **object.getClass()**, Java nhận Klass* hay Class<?> mirror?

**Đáp án:** Nhận **java.lang.Class mirror object**, không phải raw native Klass*.

**Bài 9.** Nếu JVM báo **OutOfMemoryError: Compressed class space**, nên xem những gì?

**Đáp án:** Class metadata/class-loader growth, compressed class space budget, unloading và native memory; không chỉ tăng -Xmx.

**Bài 10.** Tắt compressed oops làm stdout của chương trình so sánh references thay đổi không?

**Đáp án:** Không nếu chương trình hợp lệ và cùng điều kiện dữ liệu. Java reference identity semantics không phụ thuộc width nội bộ.

**Bài 11.** Ở JVM 64-bit với compressed oops, một local variable có kiểu Object bắt buộc chiếm đúng 4 byte trên native stack?

**Đáp án:** Không. Locals trong JVM model, compiler registers và native stack layout khác với object field/array element encoding.

**Bài 12.** Có thể đo object size chính xác bằng code **Holder.class.getDeclaredFields().length * 4 + 12** không?

**Đáp án:** Không. Cần xét types, superclass fields, field arrangement, alignment, padding và VM flags; dùng JOL/profiler phù hợp.

**Bài 13.** Hai class loaders khác nhau định nghĩa cùng class name. Header class pointer của instances có bắt buộc trỏ tới cùng Klass metadata không?

**Đáp án:** Không. Đây là các runtime classes khác nhau nên metadata tương ứng khác nhau.

**Bài 14.** **-XX:+UseCompressedOops** có bảo đảm final flag bật nếu heap quá lớn/cấu hình không tương thích không?

**Đáp án:** Không nên giả định. Runtime có thể cảnh báo, tự điều chỉnh hoặc từ chối; luôn kiểm tra final flags và VM diagnostics.

## 20. Quy trình thực hành và checklist

Khi đánh giá compressed references cho một ứng dụng HotSpot:

1. **Xác định môi trường**: JDK build, kiến trúc 64-bit, collector, OS, container limits, flags hiện hành.
2. **Đọc final flags**: UseCompressedOops, UseCompressedClassPointers, ObjectAlignmentInBytes, MaxHeapSize, CompressedClassSpaceSize.
3. **Phân tích workload**: nhiều object references/arrays hay chủ yếu là primitive buffers, off-heap memory?
4. **Lấy ví dụ một class cụ thể**: tính shallow size lý thuyết có cả header và padding; không chỉ cộng reference widths.
5. **Dùng JOL/VM tools** để quan sát layout thực; không biến ví dụ giả định thành số liệu production.
6. **Đo performance** với benchmark có warm-up, throughput/latency, GC pauses và memory footprint.
7. **Thận trọng đổi alignment**: mở rộng địa chỉ hóa có thể tăng object padding.
8. **Nếu memory error**: phân biệt Java heap, Metaspace và compressed class space.
9. **Tránh dùng internal pointers từ Java**: không đồng nhất HashCode, Java Class mirror và Klass*.
10. **Ghi chú tính phụ thuộc implementation**: hotspot flags/layout thay đổi theo JDK, không phải yêu cầu JVMS.
11. **Với plugin/dynamic class generation**, quan sát number of classes/loaders và khả năng unloading; có thể tiêu tốn compressed class space dù live heap nhỏ.
12. **Kiểm tra tính đúng đắn trước tối ưu**: thay flag phải giữ nguyên semantics của Java code và được thử nghiệm trên staging/runtime đích.

### Tài liệu đối chiếu

- **Oracle Java SE 17 — The java Command**, đặc biệt UseCompressedOops, ObjectAlignmentInBytes và các VM flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle Java SE 17 GC Tuning — Other Considerations**, gồm class metadata và compressed class pointers: https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html
- **Oracle HotSpot VM Performance Enhancements — Compressed Oops** (giải thích cơ chế, lịch sử): https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **OpenJDK JOL (Java Object Layout)**: https://github.com/openjdk/jol
- **OpenJDK HotSpot source — CompressedOops implementation**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/oops/compressedOops.hpp
- **JVMS Java SE 17 — Run-Time Data Areas**, để phân biệt mô hình JVM với implementation layout: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5

**Ghi nhớ cốt lõi:** Compressed oops dùng **narrowOop** để biểu diễn nhiều Java heap references qua 32-bit encoded offsets; compressed class pointers dùng **narrowKlass** để rút gọn phần class-metadata pointer của object header. Cả hai có thể làm nhỏ object graph, nhưng chúng không cùng miền đích, không cùng ý nghĩa và không tự bảo đảm tối ưu trong mọi workload. **32 GiB là mốc thường gặp từ 32-bit × 8-byte scaling**, không phải một câu trả lời tuyệt đối; hãy luôn đo object alignment, heap placement và flags thực tế trên HotSpot/JDK đang chạy.
