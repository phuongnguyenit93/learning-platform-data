# Record và đối tượng bất biến khi làm khóa hoặc phần tử Set

Một khóa của `HashMap` hoặc phần tử của `HashSet` không chỉ cần có `equals` và `hashCode` đúng tại lúc tạo. Thông tin mà hai phương thức dựa vào cần giữ ổn định trong thời gian đối tượng đang được dùng để tìm kiếm hoặc loại trùng.

Record và những kiểu giá trị bất biến giúp đáp ứng yêu cầu đó. Nhưng record chỉ bảo vệ các trường thành phần ở mức tham chiếu; nó không tự làm mọi đối tượng bên trong thành bất biến.

Bài này giải thích cách chọn thành phần khóa, dùng record, bảo vệ dữ liệu tham chiếu và xử lý mảng. Ví dụ dùng Java 17 trở lên.

## 1. Vì sao khóa và phần tử tập cần ổn định?

Một cấu trúc băm tổ chức dữ liệu dựa trên mã băm của khóa hoặc phần tử. Khi truy vấn, nó cần tìm theo mã băm và quan hệ bình đẳng tương ứng.

Có thể hình dung:

```text
Thêm đối tượng theo giá trị khóa hiện tại
        ↓
Lưu trong cấu trúc băm
        ↓
Tra cứu bằng cùng quan hệ giá trị
```

Nếu dữ liệu tham gia bình đẳng hoặc băm bị sửa giữa chừng, quan hệ giữa giá trị hiện tại và cách đối tượng đã được lưu có thể bị phá. Đối tượng vẫn còn trong cấu trúc, nhưng việc tìm hoặc loại bỏ theo giá trị mới có thể không được bảo đảm như mong đợi.

Hợp đồng `Map` và `Set` cảnh báo về việc thay đổi dữ liệu làm ảnh hưởng bình đẳng khi một đối tượng đang được dùng làm khóa hoặc thành viên. Không nên viết chương trình dựa vào kết quả tình cờ sau một thay đổi như vậy. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

Đối tượng bất biến giúp dễ suy luận: một khi đã được tạo hợp lệ, giá trị dùng làm khóa không đổi ngoài kiểm soát.

### Bất biến toàn bộ và ổn định phần khóa

Một đối tượng có thể có nhiều trường thay đổi nhưng chỉ dùng một mã bất biến trong `equals`/`hashCode`. Trong trường hợp ấy, những thay đổi không liên quan không nhất thiết phá khóa.

Tuy vậy, tách một **kiểu khóa giá trị bất biến** khỏi hồ sơ có thể sửa thường rõ ràng hơn:

```text
CustomerKey → chỉ thông tin xác định khách hàng
CustomerProfile → tên, liên hệ, trạng thái và dữ liệu thay đổi
Map<CustomerKey, CustomerProfile> → tra cứu hồ sơ bằng khóa ổn định
```

Không cần đưa mọi dữ liệu của hồ sơ vào khóa chỉ vì chúng có sẵn trong đối tượng.

## 2. Record cung cấp những gì?

Một khai báo:

```java
record CustomerKey(String tenantId, String customerId) {}
```

Record là một lớp mang một tập thành phần giá trị cố định. Khi không tự khai báo thay thế, Java cung cấp:

- Trường `private final` tương ứng mỗi thành phần.
- Constructor chuẩn để khởi tạo các thành phần.
- Accessor như `tenantId()` và `customerId()`.
- `equals`, `hashCode` và `toString` dựa trên các thành phần.

Lớp record không được kế thừa để thêm trạng thái đối tượng theo một hệ lớp con. Điều này giúp tránh một số vấn đề khi mở rộng nghĩa bình đẳng giữa lớp cha và lớp con.

Hai đối tượng cùng lớp record, có các thành phần tương ứng bằng nhau, được xem là bằng nhau theo cách sinh mặc định. Với các thành phần `String` trong ví dụ, bình đẳng là theo nội dung chuỗi.

```java
CustomerKey first = new CustomerKey("T1", "C7");
CustomerKey second = new CustomerKey("T1", "C7");

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

Không cần giữ đúng cùng tham chiếu để tra cứu một khóa giá trị. Một khóa mới có cùng thành phần có thể tìm được ánh xạ hoặc thành viên đã lưu. [Java 17: Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

### Record không hứa một giá trị hash cố định để lưu bền

Điều cần dựa vào là sự nhất quán với bình đẳng, không phải một công thức kết hợp số cụ thể của trình biên dịch. Không dùng `record.hashCode()` làm mã định danh duy nhất, khóa cơ sở dữ liệu, checksum trao đổi hoặc giá trị cần giữ giống nhau giữa mọi runtime.

Tương tự, `toString()` thuận tiện để đọc khi gỡ lỗi nhưng không phải định dạng tuần tự hóa để chương trình phân tích lấy lại các thành phần.

## 3. Thiết kế thành phần khóa trước khi chọn cú pháp

Record làm việc viết mã ngắn hơn; nó không tự chọn đúng nghĩa của danh tính.

Giả sử mã khách hàng chỉ duy nhất trong từng tổ chức:

```java
record CustomerKey(String tenantId, String customerId) {}
```

Hai khóa:

```text
(T1, C7)
(T2, C7)
```

phải khác nhau. Nếu chỉ dùng `customerId`, dữ liệu hai tổ chức có thể bị gộp khi loại trùng hoặc bị ghi đè trong map.

Ngược lại, khai báo một record hồ sơ gồm cả tên:

```java
record CustomerProfile(CustomerKey key, String displayName) {}
```

Theo bình đẳng mặc định, hai hồ sơ cùng khóa nhưng khác tên không bằng nhau. Đó có thể là nghĩa hợp lý cho một ảnh chụp hồ sơ, nhưng không phải nghĩa mong muốn của khóa khách hàng.

### Các câu hỏi cần trả lời

| Câu hỏi | Tác động đến thiết kế |
| --- | --- |
| Mã duy nhất trong phạm vi nào? | Có thể cần thêm tổ chức, môi trường hoặc loại tài nguyên |
| Trường nào có thể đổi? | Tránh dùng làm danh tính khóa nếu thay đổi không tạo danh tính mới |
| Hai phiên bản hồ sơ có phải cùng khóa không? | Tách khóa khỏi dữ liệu phiên bản |
| Có phân biệt hoa thường hoặc khoảng trắng không? | Cần một chính sách chuẩn hóa rõ |
| Có trạng thái “chưa có mã” không? | Không nên vô tình gộp nhiều đối tượng chưa có mã thành cùng khóa |
| Thứ tự thành phần collection có ý nghĩa không? | Chọn `List` hoặc `Set` theo đúng quan hệ giá trị |

Không tự chuẩn hóa chữ hoa, bỏ dấu hoặc cắt khoảng trắng chỉ vì thuận tiện. Mỗi phép chuẩn hóa làm thay đổi ranh giới những giá trị được xem là cùng một khóa.

## 4. Kiểm tra dữ liệu bằng compact constructor

Một record vẫn có thể kiểm tra điều kiện đầu vào:

```java
record CustomerKey(String tenantId, String customerId) {
    CustomerKey {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(customerId);

        if (tenantId.isBlank() || customerId.isBlank()) {
            throw new IllegalArgumentException("ids must not be blank");
        }
    }
}
```

Ví dụ cần import `java.util.Objects`. Đây là compact constructor cho một record có phạm vi truy cập phù hợp trong lớp minh họa.

Mục đích:

1. Không cho tạo khóa thiếu thành phần bắt buộc.
2. Phát hiện dữ liệu không hợp lệ ngay tại biên tạo giá trị.
3. Giữ cùng một điều kiện cho mọi nơi dùng khóa trong map hoặc tập.

Với compact constructor, có thể điều chỉnh giá trị tham số trước khi chúng được gán vào các trường thành phần. Điều này hữu ích cho bản sao phòng vệ hoặc một phép chuẩn hóa đã được nghiệp vụ định nghĩa.

Record không tự từ chối `null` ở thành phần tham chiếu. Nếu `null` không hợp lệ, phải kiểm tra. Bình đẳng mặc định có khả năng xử lý thành phần tham chiếu `null`, nhưng “so được” không đồng nghĩa “đúng miền dữ liệu”. [Java Language Specification 17: record và constructor](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10)

## 5. Record chỉ bất biến nông

Xét một record có danh sách:

```java
record UnsafeTagKey(List<String> tags) {}
```

Trường `tags` được giữ bằng một tham chiếu final, nhưng đối tượng danh sách được tham chiếu vẫn có thể sửa:

```java
List<String> source = new ArrayList<>(List.of("red"));
UnsafeTagKey key = new UnsafeTagKey(source);

source.add("blue");
System.out.println(key.tags()); // [red, blue]
```

Không có phép gán lại trường record nào diễn ra. Chính đối tượng danh sách bên trong đã thay đổi.

Vì `List.equals` và `List.hashCode` phụ thuộc nội dung, giá trị bình đẳng/băm của record có thành phần này cũng có thể thay đổi. Đặt record ấy vào `HashSet` hoặc dùng làm khóa map rồi sửa danh sách là rủi ro.

Có hai đường làm lọt thay đổi:

- Người gọi giữ tham chiếu danh sách đã truyền vào constructor.
- Accessor mặc định trả lại cùng tham chiếu danh sách, cho phép sửa qua `key.tags()`.

Vì vậy, không thể khẳng định một khóa an toàn chỉ bằng việc thấy từ khóa `record`.

## 6. Sao chép phòng vệ với List<String>

Nếu thứ tự thẻ là một phần của giá trị khóa, có thể thiết kế:

```java
record OrderedTagKey(List<String> tags) {
    OrderedTagKey {
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf` cho một danh sách không sửa được và không phản ánh việc thêm/xóa sau đó của nguồn. Nó cũng từ chối nguồn hoặc phần tử `null` theo hợp đồng.

Vì `String` bất biến, kết hợp này bảo vệ được cả cấu trúc danh sách và các giá trị chuỗi dùng cho khóa:

```java
List<String> source = new ArrayList<>(List.of("red"));
OrderedTagKey key = new OrderedTagKey(source);

source.add("blue");
System.out.println(key.tags()); // [red]
```

Gọi `key.tags().add("green")` sẽ bị từ chối. Accessor có thể trả danh sách không sửa được đang giữ mà không mở một đường sửa cấu trúc từ bên ngoài. [Java 17: List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

### 6.1. Vì sao chỉ unmodifiableList(source) chưa đủ?

Một view không cho sửa như `Collections.unmodifiableList(source)` vẫn gắn với nguồn. Nếu người gọi giữ `source` và sửa nó, view phản ánh thay đổi.

Muốn một ảnh chụp cấu trúc ổn định, cần cơ chế sao chép hoặc phương thức có hợp đồng không phản ánh thay đổi nguồn như `List.copyOf`, thay vì chỉ chặn sửa qua một tham chiếu.

### 6.2. CopyOf vẫn là bản sao nông

Nếu thành phần là `List<MutableItem>`, việc không cho thêm/xóa danh sách chưa ngăn một `MutableItem` bên trong thay đổi.

Nếu bình đẳng/băm của phần tử phụ thuộc trạng thái đó, khóa vẫn có thể không ổn định. Những hướng phù hợp gồm:

- Chuyển từng phần tử sang một kiểu giá trị bất biến.
- Sao chép sâu các phần thực sự cần làm khóa.
- Chỉ giữ định danh bất biến của phần tử.
- Thiết kế lại khóa để không chứa đồ thị dữ liệu thay đổi.

Không dùng “copy” như một từ đồng nghĩa với “mọi dữ liệu bên trong đã độc lập”.

### 6.3. List hay Set là một phần của nghĩa khóa

`List.of("red", "blue")` khác `List.of("blue", "red")` theo bình đẳng danh sách. Nếu thứ tự thẻ không có ý nghĩa, chọn thành phần tập giá trị bất biến, chẳng hạn một `Set<String>` được tạo bằng `Set.copyOf`, có thể đúng hơn.

Nhưng `Set` bỏ thông tin lặp; nếu số lần xuất hiện quan trọng thì lại không phù hợp. Không chuyển kiểu chỉ để làm dữ liệu “có vẻ bất biến” mà quên ngữ nghĩa bình đẳng.

## 7. Mảng trong record có hai vấn đề riêng

Xét:

```java
record ArrayComponentKey(int[] values) {}
```

Vấn đề thứ nhất là mảng có thể sửa. Constructor và accessor mặc định giữ/trả cùng tham chiếu mảng.

Vấn đề thứ hai là bình đẳng mặc định của thành phần mảng dựa vào bình đẳng của chính đối tượng mảng, không tự so từng số bên trong:

```java
ArrayComponentKey first =
        new ArrayComponentKey(new int[]{1, 2});

ArrayComponentKey second =
        new ArrayComponentKey(new int[]{1, 2});

System.out.println(first.equals(second)); // false
```

Hai mảng khác nhau dù cùng nội dung không tự làm record bằng nhau.

Đáng chú ý: sửa nội dung một mảng không nhất thiết làm hash tham chiếu mảng đổi. Nhưng điều đó không biến record này thành một khóa giá trị theo nội dung. Phải phân biệt **ổn định hash** với **đúng nghĩa bình đẳng cần có**.

Nếu yêu cầu khóa là dãy số theo nội dung, chỉ clone mảng trong constructor mà vẫn giữ bình đẳng mảng mặc định chưa giải quyết đủ. Cần đồng thời:

1. Bảo vệ mảng khỏi sửa qua đầu vào.
2. Không để accessor làm lộ mảng nội bộ có thể sửa.
3. Định nghĩa bình đẳng nội dung.
4. Tính hash nội dung tương ứng.

Một lớp bất biến tường minh thường dễ giải thích cho trường hợp này.

## 8. Lớp khóa bất biến cho nội dung mảng

Ví dụ:

```java
static final class IntArrayKey {
    private final int[] values;

    IntArrayKey(int[] values) {
        this.values = Objects.requireNonNull(values).clone();
    }

    int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof IntArrayKey key
                    && Arrays.equals(values, key.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }
}
```

Đây là lớp lồng trong chương trình minh họa, cần import `Arrays` và `Objects`.

Các lớp bảo vệ phối hợp:

- Lớp `final` không cho lớp con mở rộng trạng thái và làm mơ hồ bình đẳng.
- Trường `private final` giữ quyền sở hữu tham chiếu.
- Constructor clone mảng đầu vào.
- Accessor trả clone, không trả mảng nội bộ.
- `Arrays.equals` và `Arrays.hashCode` cùng dựa trên nội dung dãy số.

Hai khóa được tạo từ hai mảng riêng có cùng số sẽ bằng nhau. Sửa mảng truyền vào hoặc mảng nhận từ accessor không thay đổi khóa.

Clone một `int[]` đủ sao chép các giá trị primitive. Với mảng chứa đối tượng, clone chỉ sao chép các tham chiếu phần tử; vẫn phải xét trạng thái phần tử.

Không cache hash để che một thiết kế còn lộ dữ liệu sửa được. Nếu `equals` đổi theo dữ liệu mà hash đã cache không đổi, ta có thể tạo vấn đề nhất quán khác thay vì giải quyết tính bất biến. [Java 17: Arrays.equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

## 9. Nếu tùy chỉnh record, phải giữ bình đẳng và khả năng dựng lại

Record cho phép khai báo rõ constructor, accessor và các phương thức giá trị trong những giới hạn của ngôn ngữ. Điều đó không có nghĩa có thể tùy ý thay nghĩa mà không xét hợp đồng.

Một yêu cầu đáng chú ý của record: tạo lại record bằng các giá trị lấy từ accessor cần cho một giá trị bằng record gốc:

```text
copy = new R(r.c1(), r.c2(), ...)

r.equals(copy) phải đúng.
```

Nếu accessor clone mảng nhưng `equals` vẫn dùng bình đẳng tham chiếu mảng, một bản dựng lại từ accessor có thể không bằng bản gốc. Đây là một lý do không nên chỉ thêm defensive accessor rồi bỏ qua bình đẳng của thành phần.

Nếu tùy chỉnh bình đẳng của record có mảng, phải xem xét đồng thời `equals`, `hashCode`, constructor, accessor và các bất biến liên quan. Nếu giá trị không còn được mô tả tự nhiên bằng các thành phần công khai, một lớp giá trị thông thường có thể rõ hơn. [Java 17: hợp đồng Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

## 10. Tập băm và tập cây cần ổn định theo những tiêu chí khác nhau

Với `HashSet`, trạng thái tham gia `equals`/`hashCode` cần ổn định.

Với `TreeSet`, trạng thái được comparator hoặc thứ tự tự nhiên sử dụng cũng phải ổn định trong khi nằm trong cây. Một đối tượng có hash ổn định nhưng trường sắp xếp bị đổi vẫn có thể không còn nằm đúng vị trí tìm theo thứ tự.

Một kiểu khóa gồm các giá trị bất biến giúp cả hai trường hợp, nhưng vẫn phải chọn comparator phù hợp:

- Nếu comparator chỉ xét một phần khóa, hai giá trị khác nhau có thể so sánh bằng 0.
- Nếu muốn tuân thủ đầy đủ hợp đồng tập, thứ tự cần nhất quán với `equals`.
- Record không tự sinh `Comparable` hoặc một thứ tự sắp phù hợp chỉ vì nó có bình đẳng giá trị.

Chọn tập băm hay tập cây là quyết định khác với chọn record hay class. Một bên xác định cơ chế truy cập và loại trùng; bên kia xác định mô hình giá trị của phần tử. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

## 11. Thay đổi hồ sơ khác với thay đổi khóa

Với một map:

```java
Map<CustomerKey, CustomerProfile> customers = new HashMap<>();
```

Có thể cập nhật hồ sơ bằng cách thay giá trị tại cùng một khóa bất biến. Tên hiển thị đổi không cần làm khóa đổi.

Nếu danh tính thực sự đổi, hãy tạo một khóa mới và điều phối cập nhật rõ ràng. Phải xét:

- Khóa mới đã tồn tại chưa?
- Cần chuyển giá trị hay hợp nhất dữ liệu?
- Có tập hoặc chỉ mục phụ nào còn giữ khóa cũ?
- Các bên truy cập đồng thời cần quan sát chuyển đổi theo cơ chế nào?
- Nếu thao tác lỗi giữa chừng, quy trình khôi phục ra sao?

Đối tượng bất biến không tự tạo giao dịch cho các bước `remove` và `put`. Nó giúp không có chuyện đối tượng đã đặt trong cấu trúc âm thầm đổi giá trị.

Một record chứa dữ liệu bất biến cũng không tự làm `HashMap` hoặc `HashSet` dùng chung trở nên an toàn đồng thời. Tính ổn định của khóa và cơ chế phối hợp truy cập là hai điều kiện riêng.

## 12. Chương trình Java 17 hoàn chỉnh

Lưu vào `ImmutableKeyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ImmutableKeyDemo {
    record CustomerKey(String tenantId, String customerId) {
        CustomerKey {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(customerId);
            if (tenantId.isBlank() || customerId.isBlank()) {
                throw new IllegalArgumentException("ids must not be blank");
            }
        }
    }

    record CustomerProfile(CustomerKey key, String displayName) {}

    record OrderedTagKey(List<String> tags) {
        OrderedTagKey {
            tags = List.copyOf(tags);
        }
    }

    record UnsafeTagKey(List<String> tags) {}

    record ArrayComponentKey(int[] values) {}

    static final class IntArrayKey {
        private final int[] values;

        IntArrayKey(int[] values) {
            this.values = Objects.requireNonNull(values).clone();
        }

        int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof IntArrayKey key
                        && Arrays.equals(values, key.values));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        CustomerKey first = new CustomerKey("T1", "C7");
        CustomerKey equalKey = new CustomerKey("T1", "C7");
        System.out.println("record value equality = " + first.equals(equalKey));
        System.out.println("record equal hashes = "
                + (first.hashCode() == equalKey.hashCode()));

        Map<CustomerKey, String> customers = new HashMap<>();
        customers.put(first, "Lan");
        System.out.println("lookup with fresh record = " + customers.get(equalKey));
        customers.put(equalKey, "Lan updated");
        System.out.println("map size after update = " + customers.size());

        Set<CustomerKey> scoped = new HashSet<>();
        scoped.add(first);
        scoped.add(equalKey);
        scoped.add(new CustomerKey("T2", "C7"));
        System.out.println("tenant-scoped set size = " + scoped.size());

        CustomerProfile before = new CustomerProfile(first, "Lan");
        CustomerProfile after = new CustomerProfile(first, "Lan updated");
        System.out.println("profiles with changed name equal = "
                + before.equals(after));
        System.out.println("profile keys still equal = "
                + before.key().equals(after.key()));

        List<String> externalTags = new ArrayList<>(List.of("red"));
        OrderedTagKey stable = new OrderedTagKey(externalTags);
        Set<OrderedTagKey> stableSet = new HashSet<>();
        stableSet.add(stable);
        externalTags.add("blue");
        System.out.println("copied tags = " + stable.tags());
        System.out.println("stable key lookup = "
                + stableSet.contains(new OrderedTagKey(List.of("red"))));
        try {
            stable.tags().add("green");
        } catch (UnsupportedOperationException expected) {
            System.out.println("tag accessor does not allow structural mutation");
        }

        List<String> mutableTags = new ArrayList<>(List.of("red"));
        UnsafeTagKey unsafe = new UnsafeTagKey(mutableTags);
        UnsafeTagKey oldValue = new UnsafeTagKey(List.of("red"));
        System.out.println("unsafe key initially equal = " + unsafe.equals(oldValue));
        mutableTags.add("blue");
        System.out.println("unsafe key equal after external mutation = "
                + unsafe.equals(oldValue));

        ArrayComponentKey rawA = new ArrayComponentKey(new int[]{1, 2});
        ArrayComponentKey rawB = new ArrayComponentKey(new int[]{1, 2});
        System.out.println("default record array equality = " + rawA.equals(rawB));

        int[] externalArray = {1, 2};
        IntArrayKey arrayKey = new IntArrayKey(externalArray);
        Set<IntArrayKey> arrayKeys = new HashSet<>();
        arrayKeys.add(arrayKey);
        externalArray[0] = 99;
        int[] returnedArray = arrayKey.values();
        returnedArray[1] = 88;
        System.out.println("protected array value = "
                + Arrays.toString(arrayKey.values()));
        System.out.println("protected array key lookup = "
                + arrayKeys.contains(new IntArrayKey(new int[]{1, 2})));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ImmutableKeyDemo.java
java ImmutableKeyDemo
```

Stdout:

```text
record value equality = true
record equal hashes = true
lookup with fresh record = Lan
map size after update = 1
tenant-scoped set size = 2
profiles with changed name equal = false
profile keys still equal = true
copied tags = [red]
stable key lookup = true
tag accessor does not allow structural mutation
unsafe key initially equal = true
unsafe key equal after external mutation = false
default record array equality = false
protected array value = [1, 2]
protected array key lookup = true
```

Cách đọc minh chứng:

1. Hai record cùng tổ chức và mã khách hàng bằng nhau, có cùng hash và tra được cùng ánh xạ.
2. Ghi giá trị bằng khóa tương đương không tạo thêm một ánh xạ.
3. Cùng mã cục bộ ở tổ chức khác vẫn là một thành viên khác của tập.
4. Hồ sơ đổi tên là một giá trị hồ sơ khác, nhưng khóa của hai hồ sơ vẫn bằng nhau.
5. Record sao chép `List<String>` không bị ảnh hưởng khi danh sách đầu vào thêm phần tử.
6. Accessor của record ấy không cho sửa cấu trúc danh sách đang giữ.
7. Record không phòng vệ bị thay đổi giá trị quan sát được qua một alias danh sách đầu vào.
8. Hai thành phần mảng khác nhau không tự được record mặc định so theo nội dung.
9. Lớp `IntArrayKey` bảo vệ cả đường vào lẫn đường ra, nên sửa các mảng bên ngoài không ảnh hưởng tra cứu.

Chương trình không truy vấn tập sau khi cố tình làm hỏng một khóa đã lưu. Phần “unsafe” chỉ so giá trị trước và sau thay đổi để minh chứng bất biến nông, tránh hứa một output tra cứu cụ thể cho trạng thái dùng khóa không an toàn.

Nó cũng không in giá trị hash record cố định hoặc thứ tự `HashSet`/`HashMap`, nên kết quả không dựa vào những chi tiết không cần thiết của cách triển khai.

## 13. Cách kiểm chứng một kiểu khóa bất biến

Một bộ kiểm tra có ý nghĩa nên bao gồm:

1. Tạo hai khóa riêng có cùng giá trị và xác nhận `equals`.
2. Xác nhận các khóa bằng nhau có cùng hash.
3. Tra bằng một khóa mới cùng giá trị trong map/tập.
4. Xác nhận thành phần phạm vi khác làm khóa khác nếu đó là yêu cầu.
5. Thử sửa dữ liệu đầu vào sau khi tạo và xác nhận khóa không đổi.
6. Thử sửa dữ liệu lấy từ accessor và xác nhận không làm thay đổi khóa.
7. Kiểm tra phần tử lồng nhau, không chỉ container ngoài.
8. Kiểm tra dữ liệu không hợp lệ được từ chối theo hợp đồng.
9. Nếu có comparator, kiểm tra tính tương thích với bình đẳng.
10. Nếu tùy chỉnh record, kiểm tra giá trị dựng lại từ accessor bằng giá trị ban đầu.

Không kiểm tra “hai khóa khác nhau bắt buộc có hash khác nhau”: va chạm được phép. Không dùng một giá trị hash cố định làm bằng chứng chung cho tính đúng đắn của record.

## 14. Lỗi thường gặp

| Hiểu nhầm | Điều cần nhớ |
| --- | --- |
| Có từ khóa record thì mọi dữ liệu bên trong bất biến | Record chỉ giữ cố định các trường thành phần; đối tượng tham chiếu vẫn có thể sửa |
| Trường final ngăn sửa nội dung danh sách hoặc mảng | Final ngăn gán lại tham chiếu, không tự đóng băng đối tượng |
| `List.copyOf` tạo bản sao sâu | Nó không tự sao chép đối tượng phần tử |
| Bọc nguồn bằng unmodifiable view là đủ | Nguồn có thể đổi qua alias khác |
| Record có mảng tự so theo nội dung mảng | Bình đẳng mặc định không thay bằng `Arrays.equals` |
| Clone mảng khi nhận vào là đủ | Accessor trả mảng nội bộ vẫn làm lộ đường sửa |
| Cache hash có thể cứu một khóa còn thay đổi | Bình đẳng và hash có thể trở nên không nhất quán |
| Mọi trường hồ sơ đều nên là thành phần khóa | Chọn theo danh tính giá trị cần dùng, tránh dữ liệu dễ đổi |
| Record tự có thứ tự tự nhiên phù hợp TreeSet | Phải định nghĩa Comparable hoặc comparator phù hợp |
| Khóa bất biến làm collection an toàn đồng thời | Cơ chế phối hợp truy cập vẫn cần riêng |

## 15. Tự luyện

1. `record Key(List<String> ids) {}` có an toàn làm khóa băm nếu người gọi còn giữ một `ArrayList` đã truyền vào không?  
   **Đáp án:** chưa. Người gọi có thể sửa danh sách làm thay đổi giá trị khóa.

2. Vì sao `List.copyOf` phù hợp hơn một view không cho sửa khi cần ảnh chụp danh sách chuỗi?  
   **Đáp án:** kết quả không phản ánh thêm/xóa sau đó của nguồn; với `String` bất biến, các giá trị thành phần cũng ổn định.

3. Hai record cùng kiểu chứa hai mảng `int[]` riêng có cùng số bên trong có mặc định bằng nhau không?  
   **Đáp án:** không. Cần một thiết kế bình đẳng nội dung nếu đó là yêu cầu.

4. Khách hàng đổi tên hiển thị. Có nên tạo khóa khách hàng khác chỉ vì record hồ sơ có thêm trường tên không?  
   **Gợi ý:** tách khóa ổn định khỏi hồ sơ và xác định rõ danh tính nghiệp vụ.

5. Có thể dùng record chứa `List<MutableItem>` làm khóa chỉ bằng `List.copyOf` không?  
   **Đáp án:** chưa đủ nếu trạng thái phần tử tham gia bình đẳng/băm còn có thể thay đổi.

Một kiểu khóa tốt giữ đúng nghĩa danh tính và không để thông tin dùng cho tìm kiếm thay đổi ngoài kiểm soát. Record giúp biểu diễn ngắn gọn; tính bất biến thực sự vẫn cần được thiết kế đến tận các thành phần bên trong.
