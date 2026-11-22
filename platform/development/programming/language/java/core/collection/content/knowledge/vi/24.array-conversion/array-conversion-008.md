# Chọn loại collection đích để bảo toàn hợp đồng cần thiết

## 1. Chuyển đổi thành công chưa có nghĩa giữ đúng ý nghĩa dữ liệu

Giả sử một danh sách dòng đặt hàng chứa hai dòng có cùng giá trị. Nếu chuyển nó thành `HashSet` để “tra cứu cho nhanh”, những dòng bằng nhau có thể bị gộp và thứ tự không còn được cam kết. Chương trình vẫn biên dịch, không nhất thiết có ngoại lệ, nhưng ý nghĩa của dữ liệu đã thay đổi.

Trong một yêu cầu khác, ứng dụng lại muốn danh sách mã không trùng, giữ lần xuất hiện đầu tiên. Khi đó, việc gộp phần tử là chủ ý và `LinkedHashSet` có thể phù hợp hơn. Cùng một nguồn dữ liệu nhưng mục tiêu sử dụng khác nhau dẫn đến lựa chọn đích khác nhau.

**Hợp đồng** (contract) là những điều API hứa với bên sử dụng: cách hiểu phần tử, thứ tự, quy tắc trùng, thao tác được phép, giới hạn dữ liệu và cách truy cập. Chọn collection đích là chọn một tập hợp các cam kết ấy cho dữ liệu sau chuyển đổi.

Cần tách hai mức:

- **Trạng thái hiện tại:** kết quả đang chứa phần tử nào và đang được duyệt theo thứ tự nào.
- **Hành vi về sau:** khi thêm, xóa, truy vấn hoặc xử lý phần tử tiếp theo, cấu trúc sẽ duy trì quy tắc gì.

Ví dụ, một `ArrayList` sao chép từ `TreeSet` có thể ban đầu được duyệt theo thứ tự đã sắp xếp của nguồn. Nhưng việc thêm phần tử vào cuối list không tự sắp xếp lại nó. Giữ đúng dãy hiện tại không đồng nghĩa giữ hợp đồng “luôn có thứ tự theo bộ so sánh”.

Một mô hình suy nghĩ hữu ích:

```text
Nguồn
  -> xác định những thông tin và hành vi phải giữ
  -> chọn giao diện, lớp triển khai và cách tạo đích
  -> chuyển phần tử theo chính sách đã chọn
  -> kiểm tra cả nội dung lẫn thao tác về sau
```

Mục tiêu không phải sao chép mọi đặc điểm của nguồn bằng mọi giá. Mục tiêu là giữ đúng những cam kết mà API đích và nghiệp vụ thực sự cần, đồng thời nêu rõ các thay đổi có chủ ý.

## 2. Xác định hợp đồng trước khi chọn tên lớp

Trước một phép chuyển đổi, nên xác định các trục sau:

| Trục cần quyết định | Câu hỏi cụ thể |
| --- | --- |
| Số lần xuất hiện | Hai phần tử bằng nhau có còn là hai dòng riêng không? |
| Thứ tự | Cần thứ tự gặp, thứ tự sắp xếp hay thứ tự lấy ra xử lý? |
| Quy tắc bằng nhau | Dùng `equals/hashCode`, bộ so sánh hay nhận dạng tham chiếu? |
| Giá trị hợp lệ | Có `null`, enum, kiểu không hỗ trợ so sánh tự nhiên hoặc giới hạn miền không? |
| Quyền sửa | Bên nhận được thêm/xóa/thay phần tử, hay chỉ đọc? |
| Liên hệ với nguồn | Cần khung nhìn phản ánh thay đổi của nguồn hay kết quả độc lập về cấu trúc? |
| Khả năng thao tác | Cần chỉ số, truy vấn phạm vi, hai đầu hàng đợi, lấy theo ưu tiên hay chờ khi đầy/rỗng? |
| Truy cập đồng thời | Kết quả có được nhiều luồng chia sẻ; cần những thao tác nguyên tử nào? |

Kiểu `Collection<E>` không biểu diễn đầy đủ các trục này. Nó không hứa một thứ tự chung, không yêu cầu mọi lớp đều cho thêm phần tử và không mang theo một bộ so sánh của nguồn như tham số kiểu.

Ngay cả biến `List<String>` cũng không tự cam kết rằng `add` sẽ được phép. Một list không cho sửa và một `ArrayList` cùng có thể được nhìn qua giao diện `List`. Khai báo biến là `final` cũng chỉ ngăn gán lại biến, không tự cấm sửa đối tượng collection.

Vì vậy, một phép chuyển đổi cần được đánh giá qua cả **loại đích** và **cách tạo đích**, không chỉ qua việc kết quả có gán được cho biến cùng tham số kiểu hay không. [Hợp đồng `Collection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) mô tả các khác biệt về thứ tự, thao tác tùy chọn và chính sách của từng lớp triển khai.

### 2.1. Bảng định hướng một số đích thường gặp

| Đích | Đặc điểm nổi bật | Điều có thể thay đổi so với nguồn |
| --- | --- | --- |
| `ArrayList` | Dãy phần tử, giữ thứ tự duyệt khi sao chép, giữ phần tử trùng | Không tự giữ bộ so sánh, tính duy nhất hay chính sách chỉ đọc của nguồn |
| `LinkedHashSet` | Gộp phần tử theo `equals/hashCode`, giữ thứ tự chèn | Mất số lần xuất hiện của phần tử trùng; không tự duy trì thứ tự sắp xếp |
| `HashSet` | Tập hợp theo `equals/hashCode` | Không cam kết thứ tự duyệt |
| `TreeSet` | Sắp xếp và nhận diện trùng theo phép so sánh | Có thể gộp các giá trị khác nhau theo `equals` nếu bộ so sánh không phù hợp |
| `EnumSet` | Tập hợp chuyên cho một kiểu enum, duyệt theo thứ tự khai báo | Không giữ số lần xuất hiện hoặc thứ tự tùy ý của nguồn |
| `ArrayDeque` | Thao tác hai đầu, hỗ trợ cách dùng hàng đợi/ngăn xếp | Không nhận `null`, không mang sẵn giới hạn dung lượng cố định |
| `PriorityQueue` | Lấy phần tử theo ưu tiên | Thứ tự duyệt không phải dãy lấy ra theo ưu tiên |
| `List.copyOf(source)` | List không cho sửa, giữ dãy phần tử, không phản ánh thay đổi cấu trúc nguồn về sau | Không nhận `null`, không làm phần tử thành bất biến sâu |
| `Collections.unmodifiableList(new ArrayList<>(source))` | List chỉ đọc qua kết quả, sao chép cấu trúc và chấp nhận phần tử `null` | Các đối tượng phần tử vẫn có thể được chia sẻ |

Bảng là điểm bắt đầu để chọn hợp đồng, không phải bảng thay thế mọi API cho nhau. Những yêu cầu chuyên biệt như ràng buộc phạm vi, đồng bộ hoặc dung lượng cần được xử lý thêm.

## 3. Giữ số lần xuất hiện, thứ tự và quy tắc trùng

### 3.1. Chuyển list thành set là một phép biến đổi có mất thông tin

Một dãy `[b, a, b]` có ba vị trí, trong đó `b` xuất hiện hai lần. Một set thông thường theo `equals` chỉ giữ một đại diện của `b`. Chuyển set ấy ngược về list không khôi phục được vị trí và số lần xuất hiện đã mất.

Nếu mỗi lần xuất hiện có ý nghĩa nghiệp vụ, hãy giữ kiểu dãy hoặc một mô hình biểu diễn số lượng. Đừng chọn set chỉ vì muốn loại bỏ việc duyệt tuyến tính mà chưa xác định liệu dữ liệu có được phép bị gộp hay không.

Nếu cần **sắp xếp nhưng giữ phần tử trùng**, có thể tạo `ArrayList` rồi sắp xếp list bằng bộ so sánh phù hợp. `TreeSet` đồng thời áp dụng tính duy nhất theo phép so sánh; nó không phải một cách thay thế trong suốt cho “list được sắp xếp”.

### 3.2. Thứ tự gặp không phải lịch sử có thể khôi phục từ mọi nguồn

`new ArrayList<>(source)` lấy phần tử theo thứ tự iterator của nguồn. `LinkedHashSet` cũng giữ thứ tự chèn các đại diện được chấp nhận trong quá trình sao chép.

Nếu nguồn đã có thứ tự xác định, điều này hữu ích. Nếu nguồn là một `HashSet` không cam kết thứ tự, sao chép sang `LinkedHashSet` chỉ cố định thứ tự đã quan sát trong lần sao chép ấy. Nó không tìm lại thứ tự chèn lịch sử vốn không được nguồn cung cấp.

Với phần tử trùng, thêm lại một giá trị đã có vào `LinkedHashSet` không đẩy giá trị ấy xuống cuối. Điều đó phù hợp với yêu cầu giữ vị trí lần gặp đầu tiên theo quy tắc bằng nhau của set.

[`ArrayList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) và [`LinkedHashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) nêu rõ cách nhận thứ tự từ nguồn; [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) không cung cấp cam kết thứ tự tương ứng.

### 3.3. Có ba quy tắc nhận diện khác nhau cần phân biệt

- Set băm thông thường dùng ý nghĩa của `equals` kết hợp hợp đồng `hashCode`.
- `TreeSet` xác định hai phần tử trùng về phía cây khi phép so sánh trả về `0`.
- Một cấu trúc chuyên dùng theo nhận dạng tham chiếu có thể coi hai đối tượng chỉ trùng nếu chúng là cùng đối tượng theo `==`.

Hai chuỗi `"ID"` và `"id"` không bằng nhau theo `String.equals`, nhưng bộ so sánh không phân biệt hoa thường xem chúng tương đương. Chọn bộ so sánh ấy cho `TreeSet` có thể làm số phần tử giảm.

Đây là một tình huống để phát hiện lựa chọn không phù hợp, không phải lời khuyên bỏ qua hợp đồng chung của `Set`. Bộ so sánh của tập hợp được sắp xếp cần nhất quán với `equals` để tuân thủ hợp đồng set thông thường. Nếu nghiệp vụ cần một dạng chuẩn hóa khác, hãy thiết kế khóa/giá trị chuẩn hóa và quy tắc bằng nhau một cách rõ ràng.

Cấu trúc theo nhận dạng tham chiếu cũng là một lựa chọn chuyên biệt. Chuyển nó sang `HashSet` thông thường có thể gộp các đối tượng khác nhau nhưng có giá trị bằng nhau. Không dùng một set kiểu đó thay thế trong suốt cho mọi set theo giá trị. [`IdentityHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html) giải thích rõ trường hợp đặc biệt cần so sánh tham chiếu.

### 3.4. Chương trình 1: Một nguồn, nhiều hợp đồng đích

Tệp `TargetSemanticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class TargetSemanticsDemo {
    public static void main(String[] args) {
        List<String> source = Arrays.asList("b", "a", "b", null);
        List<String> list = new ArrayList<>(source);
        Set<String> insertionSet = new LinkedHashSet<>(source);
        Set<String> hashSet = new HashSet<>(source);

        System.out.println("source=" + source);
        System.out.println("list=" + list);
        System.out.println("insertionSet=" + insertionSet);
        System.out.println("hashSize=" + hashSet.size());
        System.out.println("hashContainsNull=" + hashSet.contains(null));
        System.out.println("roundTrip=" + new ArrayList<>(insertionSet));

        try {
            new TreeSet<>(source);
            throw new AssertionError("Natural-order TreeSet accepted null");
        } catch (NullPointerException expected) {
            System.out.println("naturalTree=NullPointerException");
        }

        TreeSet<String> nullableSorted =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullableSorted.addAll(source);
        System.out.println("nullableSorted=" + nullableSorted);

        List<String> sortedSequence = new ArrayList<>(source);
        sortedSequence.sort(Comparator.nullsFirst(Comparator.naturalOrder()));
        System.out.println("sortedSequence=" + sortedSequence);

        List<String> codes = List.of("ID", "id");
        Set<String> exactCodes = new LinkedHashSet<>(codes);
        TreeSet<String> foldedCodes = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        foldedCodes.addAll(codes);
        System.out.println("equalsDistinct=" + exactCodes.size());
        System.out.println("comparatorDistinct=" + foldedCodes.size());

        Set<String> identitySet =
                Collections.newSetFromMap(new IdentityHashMap<>());
        identitySet.add(new String("same"));
        identitySet.add(new String("same"));
        System.out.println("identitySize=" + identitySet.size());
        System.out.println("equalsCopySize=" + new HashSet<>(identitySet).size());

        list.add("tail");
        System.out.println("editableCopy=" + list);
        System.out.println("sourceSize=" + source.size());
    }
}
```

Biên dịch và chạy bằng JDK hỗ trợ Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 TargetSemanticsDemo.java
java TargetSemanticsDemo
```

Đầu ra:

```text
source=[b, a, b, null]
list=[b, a, b, null]
insertionSet=[b, a, null]
hashSize=3
hashContainsNull=true
roundTrip=[b, a, null]
naturalTree=NullPointerException
nullableSorted=[null, a, b]
sortedSequence=[null, a, b, b]
equalsDistinct=2
comparatorDistinct=1
identitySize=2
equalsCopySize=1
editableCopy=[b, a, b, null, tail]
sourceSize=4
```

Trong kết quả:

- `list` giữ đủ bốn vị trí, gồm hai lần `b` và một `null`.
- `insertionSet` giữ lần gặp đầu tiên của mỗi giá trị theo `equals`.
- `hashSet` chỉ được kiểm tra kích thước và khả năng chứa `null`; chương trình không dựng một đầu ra có thứ tự mà API không cam kết.
- `nullableSorted` vừa sắp xếp vừa gộp, còn `sortedSequence` sắp xếp nhưng giữ hai lần `b`.
- `equalsDistinct` và `comparatorDistinct` cho thấy thay quy tắc trùng có thể đổi số phần tử.
- `identitySize` và `equalsCopySize` cho thấy hai đối tượng chuỗi khác nhau có thể bị gộp khi chuyển sang quy tắc bằng nhau theo giá trị.

Nguồn được tạo bằng `Arrays.asList`, nên có kích thước cố định. Bản sao `ArrayList` vẫn cho thêm `"tail"`; nguồn giữ kích thước bốn. Đây là một thay đổi về khả năng thao tác, dù trước lời gọi `add` cả hai dãy có cùng nội dung.

Bộ so sánh `nullsFirst` trong ví dụ là lựa chọn tường minh để xử lý `null`. Nó không có nghĩa mọi `TreeSet` mặc định đều nhận `null`.

## 4. Bộ so sánh và giới hạn của nguồn không tự đi theo mọi bản sao

### 4.1. Cùng một đối tượng, khác overload, khác thứ tự

`TreeSet` có các hàm khởi tạo (constructor) được nạp chồng (overload): một hàm nhận `Collection`, hàm khác nhận `SortedSet`. Chúng có hợp đồng khác nhau:

| Cách tạo | Quy tắc thứ tự |
| --- | --- |
| `new TreeSet<>(collection)` | Thứ tự tự nhiên của phần tử |
| `new TreeSet<>(sortedSet)` | Giữ quy tắc thứ tự của tập hợp được sắp xếp được cung cấp |
| `new TreeSet<>(comparator)` rồi `addAll` | Dùng bộ so sánh được truyền tường minh |

Lựa chọn overload diễn ra dựa trên kiểu mà trình biên dịch thấy ở biểu thức đối số. Một đối tượng `TreeSet` dùng thứ tự giảm dần nhưng được truyền qua biến `Collection<Integer>` không buộc hàm khởi tạo nhận `Collection` tự sao chép bộ so sánh của nó.

Điều này có thể chỉ làm đổi thứ tự nếu phần tử có thứ tự tự nhiên. Với một kiểu đối tượng chỉ được so sánh nhờ bộ so sánh tùy chỉnh, mất bộ so sánh còn có thể khiến việc thêm phần tử vào cây thất bại bằng `ClassCastException`.

Nếu phương thức chuyển đổi phải giữ sắp xếp, có thể thiết kế chữ ký nhận `SortedSet` phù hợp hoặc nhận thêm `Comparator`. Đừng giấu thông tin cần thiết trong một tham số `Collection` rồi kỳ vọng mọi hàm khởi tạo đoán lại được.

`TreeMap` có cặp hàm khởi tạo tương tự nhận `Map` và `SortedMap`. `Map` không thuộc giao diện `Collection`, nhưng nguyên tắc chọn đích và giữ bộ so sánh cũng áp dụng khi chuyển đổi các ánh xạ.

[`TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html) và [`TreeMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) công bố rõ hợp đồng của từng hàm khởi tạo. Cần đọc theo overload thực sự được gọi.

### 4.2. Giữ bộ so sánh chưa có nghĩa giữ giới hạn của khung nhìn

Một khung nhìn (view) lấy từ `subSet` có thể chỉ cho phép các giá trị nằm trong một khoảng. Tạo `new TreeSet<>(view)` sao chép các phần tử hiện có và có thể giữ bộ so sánh nhờ overload nhận `SortedSet`. Kết quả là một cây mới, không tự mang theo giới hạn khoảng của khung nhìn gốc.

Nếu API cần một đích độc lập về cấu trúc nhưng vẫn giới hạn miền giá trị, phải áp dụng giới hạn đó một cách tường minh sau khi xây dựng cấu trúc riêng, hoặc đặt quy tắc xác thực ở một lớp API phù hợp. Một bản sao hiện chứa toàn giá trị hợp lệ không tự từ chối giá trị ngoài miền trong tương lai.

Tương tự, sao chép nội dung hiện tại của một map có thứ tự truy cập không có nghĩa sao chép luôn chính sách cập nhật thứ tự khi `get`. Chẳng hạn, hàm khởi tạo `LinkedHashMap(Map)` tạo map theo thứ tự chèn; muốn chính sách thứ tự truy cập phải chọn cách cấu hình tương ứng. [API `LinkedHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html) tách hai chính sách ấy.

### 4.3. Chương trình 2: Comparator, overload và giới hạn khoảng

Tệp `SortedCopyContractDemo.java`:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.Map;
import java.util.NavigableSet;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class SortedCopyContractDemo {
    public static void main(String[] args) {
        TreeSet<Integer> source = new TreeSet<>(Collections.reverseOrder());
        source.addAll(java.util.List.of(5, 9, 7));

        SortedSet<Integer> sortedInput = source;
        Collection<Integer> generalInput = source;
        TreeSet<Integer> preserved = new TreeSet<>(sortedInput);
        TreeSet<Integer> natural = new TreeSet<>(generalInput);
        TreeSet<Integer> explicit = new TreeSet<>(source.comparator());
        explicit.addAll(generalInput);

        preserved.add(6);
        natural.add(6);
        explicit.add(6);
        System.out.println("source=" + source);
        System.out.println("preserved=" + preserved);
        System.out.println("natural=" + natural);
        System.out.println("explicit=" + explicit);

        NavigableSet<Integer> bounded = source.subSet(9, true, 5, false);
        TreeSet<Integer> unboundedCopy = new TreeSet<>(bounded);
        try {
            bounded.add(3);
            throw new AssertionError("Range accepted an out-of-range value");
        } catch (IllegalArgumentException expected) {
            System.out.println("rangeAdd=IllegalArgumentException");
        }
        unboundedCopy.add(3);
        System.out.println("bounded=" + bounded);
        System.out.println("unboundedCopy=" + unboundedCopy);

        TreeMap<Integer, String> sortedMap =
                new TreeMap<>(Collections.reverseOrder());
        sortedMap.put(1, "one");
        sortedMap.put(3, "three");
        sortedMap.put(2, "two");

        SortedMap<Integer, String> sortedMapInput = sortedMap;
        Map<Integer, String> generalMapInput = sortedMap;
        TreeMap<Integer, String> sameOrder = new TreeMap<>(sortedMapInput);
        TreeMap<Integer, String> naturalOrder = new TreeMap<>(generalMapInput);
        System.out.println("mapSortedInput=" + sameOrder);
        System.out.println("mapGeneralInput=" + naturalOrder);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SortedCopyContractDemo.java
java SortedCopyContractDemo
```

Đầu ra:

```text
source=[9, 7, 5]
preserved=[9, 7, 6, 5]
natural=[5, 6, 7, 9]
explicit=[9, 7, 6, 5]
rangeAdd=IllegalArgumentException
bounded=[9, 7]
unboundedCopy=[9, 7, 3]
mapSortedInput={3=three, 2=two, 1=one}
mapGeneralInput={1=one, 2=two, 3=three}
```

Hai biến `sortedInput` và `generalInput` cùng trỏ tới `source`. Chúng làm hàm khởi tạo được chọn khác nhau. Khi thêm `6`, một đích tiếp tục duy trì thứ tự giảm dần, còn đích chọn thứ tự tự nhiên duy trì tăng dần.

Biến `explicit` cho thấy cách cung cấp bộ so sánh rõ ràng khi đầu vào được nhìn như collection tổng quát. Khi `comparator()` trả về `null`, điều đó biểu diễn thứ tự tự nhiên; nó không tự là một lỗi thiếu cấu hình.

Trong khoảng giảm dần từ `9` đến trước `5`, view `bounded` chứa `9` và `7`. Thêm `3` qua khung nhìn bị từ chối. Bản sao cây lại nhận `3`, vì giới hạn khoảng không thuộc hợp đồng của cây mới.

Phần map xác nhận cùng một khác biệt: nhận nguồn qua `SortedMap` giữ thứ tự giảm dần, còn nhận qua `Map` tạo cây theo thứ tự tự nhiên. Các ánh xạ hiện có giống nhau nhưng hợp đồng thứ tự đã khác.

## 5. Quyền sửa, tính độc lập và trạng thái phần tử là ba điều khác nhau

Khi bàn về “bản sao không thay đổi”, cần diễn đạt chính xác điều muốn giữ:

| Câu hỏi | Ý nghĩa |
| --- | --- |
| Có được gọi `add/remove/set` qua kết quả không? | Quyền sửa cấu trúc qua tham chiếu được cung cấp |
| Nguồn đổi cấu trúc thì kết quả có đổi theo không? | Kết quả là khung nhìn sống hay độc lập về cấu trúc |
| Đối tượng phần tử bị sửa thì có nhìn thấy qua kết quả không? | Các phần tử có đang được chia sẻ và có thể thay đổi không? |

`Collections.unmodifiableList(source)` chặn các thao tác sửa qua lớp bọc nhưng vẫn đọc dữ liệu từ `source`. Nếu bên khác còn được sửa nguồn, kết quả có thể thay đổi theo.

`List.copyOf(source)` cung cấp list không cho sửa, không phản ánh các lần thay đổi cấu trúc nguồn về sau. Tuy nhiên, nó cấm phần tử `null` và không tự sao chép sâu từng đối tượng phần tử.

`new ArrayList<>(readOnlySource)` lại tạo một list cho phép sửa. Điều này có thể đúng khi cần vùng làm việc riêng, nhưng không được coi là đã giữ chính sách chỉ đọc của API nguồn.

Nếu cần giữ dãy phần tử, chấp nhận `null` và không cho người nhận sửa cấu trúc, có thể tạo một `ArrayList` riêng rồi bọc nó bằng `unmodifiableList`. Không trao thêm tham chiếu có quyền sửa tới list riêng đó nếu hợp đồng cần sự ổn định về cấu trúc.

[`Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) và [`List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) phục vụ hai quan hệ với nguồn khác nhau.

### 5.1. Kết quả không cho sửa không làm đối tượng phần tử thành bất biến

Các hàm khởi tạo sao chép collection thông thường chủ yếu sao chép tham chiếu. Một `Customer` có trường địa chỉ thay đổi được vẫn có thể được cùng nguồn và đích tham chiếu tới. Sửa đối tượng ấy không giống với thêm hay xóa phần tử của collection.

Nếu yêu cầu là một ảnh chụp dữ liệu nghiệp vụ ổn định hoàn toàn, cần xét cả mô hình phần tử: dùng đối tượng bất biến hoặc tạo bản sao phù hợp cho từng đối tượng. Chỉ đổi lớp collection không đáp ứng được yêu cầu sâu đó.

Tương tự, đưa một đối tượng có trạng thái thay đổi vào set/map không sửa được một thiết kế `equals/hashCode` không ổn định. Nếu các trường tham gia băm hoặc so sánh thay đổi khi đối tượng đang là phần tử/khóa, collection đích có thể không còn đáp ứng cách tra cứu mà ứng dụng kỳ vọng.

### 5.2. Không suy ra giữ thứ tự từ tên copyOf

`Set.copyOf` trả về một set không cho sửa và cấm `null`, nhưng không hứa giữ thứ tự gặp của một list hay thứ tự chèn của `LinkedHashSet`. Khi đầu vào có phần tử trùng, một đại diện được giữ mà API không hứa đó là đại diện gặp đầu tiên.

Nếu yêu cầu là “không trùng, giữ lần gặp đầu, thứ tự xác định theo nguồn, không cho sửa qua kết quả”, có thể chủ động tạo `LinkedHashSet` rồi bọc bằng `Collections.unmodifiableSet`. Nếu còn cần giao diện sorted/navigable, chọn lớp bọc bảo toàn chính giao diện ấy thay vì chỉ trả một set tổng quát.

[`Set.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) định nghĩa hợp đồng riêng. Một hàm có tên “copy” không cam kết giữ mọi đặc điểm của nguồn, cũng không bắt buộc tạo một đối tượng mới nếu có thể đáp ứng hợp đồng bằng cách khác.

## 6. Những khả năng chuyên biệt cần được chọn tường minh

### 6.1. EnumSet: kiểu enum và đầu vào rỗng

`EnumSet` phù hợp khi miền giá trị là một kiểu enum và cần ý nghĩa tập hợp. Nó không giữ các lần lặp và duyệt theo thứ tự khai báo hằng enum, không theo thứ tự tùy ý của list nguồn.

Với một collection rỗng thông thường, `EnumSet.copyOf(collection)` không có phần tử để suy ra kiểu enum và ném `IllegalArgumentException`. Có thể cung cấp kiểu tường minh qua `EnumSet.noneOf(Permission.class)`, rồi thêm các phần tử.

Không diễn giải thành “mọi EnumSet rỗng đều không sao chép được”. Một `EnumSet` đã giữ thông tin kiểu của nó ngay cả khi rỗng. Hợp đồng `copyOf` cũng xử lý nguồn là một đối tượng `EnumSet` theo cách phù hợp, kể cả khi nhận qua overload `Collection`.

[API `EnumSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html) quy định rõ kiểu phần tử, thứ tự và khác biệt của nguồn rỗng.

### 6.2. Hàng đợi ưu tiên: giữ quy tắc lấy ra, không chỉ sao chép thứ tự duyệt

`PriorityQueue` giữ phần tử để lấy ra theo bộ so sánh. Iterator của nó không cam kết duyệt thành một dãy đã sắp xếp. Vì vậy, `new ArrayList<>(priorityQueue)` không có nghĩa đã tạo danh sách theo thứ tự các lần `poll`.

Nếu cần một bản sao vẫn xử lý theo ưu tiên, hàm khởi tạo nhận một `PriorityQueue` khác giữ quy tắc thứ tự tương ứng. Muốn một list theo thứ tự xử lý, có thể lấy dần từ một bản sao hàng đợi để không làm cạn nguồn.

Cũng không nên tổng quát hóa rằng mọi hàm khởi tạo nhận `Collection` đều bỏ bộ so sánh. `PriorityQueue(Collection)` có quy tắc riêng khi nguồn thực tế là `SortedSet` hoặc `PriorityQueue`. Đây là lý do phải đọc API của loại đích cụ thể.

Nếu các phần tử có cùng mức ưu tiên còn phải được xử lý theo thứ tự đến, cần một quy tắc phụ và thông tin đủ để phân biệt thứ tự ấy. Chỉ chọn `PriorityQueue` không tự tạo cam kết ổn định cho mọi cặp cùng ưu tiên.

[API `PriorityQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html) phân biệt thứ tự lấy phần tử với thứ tự duyệt và mô tả các hàm khởi tạo.

### 6.3. Dung lượng, chờ và truy cập đồng thời không nằm trong các phần tử

Chuyển một `ArrayBlockingQueue` đầy sang `ArrayDeque` có thể giữ dãy phần tử đang quan sát nhưng mất giới hạn dung lượng cố định và các thao tác chờ của hàng đợi có khả năng chờ (blocking queue).

Giá trị dung lượng ban đầu truyền cho `ArrayDeque` cũng không biến nó thành hàng đợi có giới hạn cố định như `ArrayBlockingQueue`. Hai loại cùng có thể phục vụ một luồng công việc theo FIFO nhưng có hợp đồng nhận thêm dữ liệu khác nhau.

Tương tự, tạo một `ArrayList` từ một collection an toàn cho nhiều luồng không làm list mới tự được đồng bộ. Chính sách của đích phải được chọn lại theo cách mà các luồng sẽ sử dụng kết quả.

Nếu cần đích có giới hạn, phải chọn dung lượng, chính sách khi đầy và các thao tác phù hợp. Nếu cần truy cập đồng thời, phải xét thêm các chuỗi thao tác nguyên tử, không chỉ việc một phương thức đơn lẻ có cơ chế đồng bộ hay không.

[`ArrayDeque`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html) và [`ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html) công bố các chính sách rất khác nhau dù đều có thể chứa một dãy công việc.

### 6.4. Chương trình 3: Chỉ đọc, enum, ưu tiên và dung lượng

Tệp `TargetCapabilitiesDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.concurrent.ArrayBlockingQueue;

public class TargetCapabilitiesDemo {
    private enum Permission {
        READ, WRITE
    }

    private static void failsWith(String name,
            Class<? extends RuntimeException> expected, Runnable operation) {
        try {
            operation.run();
        } catch (RuntimeException failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(name + " threw the wrong exception", failure);
            }
            System.out.println(name + "=" + failure.getClass().getSimpleName());
            return;
        }
        throw new AssertionError(name + " did not fail");
    }

    private static void ownership() {
        List<String> source = new ArrayList<>(List.of("alpha"));
        List<String> live = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> editable = new ArrayList<>(snapshot);

        source.add("beta");
        editable.add("local");
        System.out.println("live=" + live);
        System.out.println("snapshot=" + snapshot);
        System.out.println("editable=" + editable);
        failsWith("snapshotAdd", UnsupportedOperationException.class,
                () -> snapshot.add("other"));

        List<String> nullable = Arrays.asList("value", null);
        failsWith("copyOfNull", NullPointerException.class,
                () -> List.copyOf(nullable));
        List<String> nullableSnapshot =
                Collections.unmodifiableList(new ArrayList<>(nullable));
        System.out.println("nullableSnapshot=" + nullableSnapshot);
    }

    private static void enumTarget() {
        List<Permission> input =
                List.of(Permission.WRITE, Permission.READ, Permission.WRITE);
        System.out.println("enumInput=" + input);
        System.out.println("enumTarget=" + EnumSet.copyOf(input));

        List<Permission> empty = List.of();
        failsWith("enumEmptyList", IllegalArgumentException.class,
                () -> EnumSet.copyOf(empty));
        EnumSet<Permission> safeEmpty = EnumSet.noneOf(Permission.class);
        safeEmpty.addAll(empty);
        System.out.println("enumExplicitEmpty=" + safeEmpty);
        System.out.println("enumEmptySetCopy=" + EnumSet.copyOf(safeEmpty));
    }

    private static void queueTarget() {
        PriorityQueue<Integer> priority =
                new PriorityQueue<>(Collections.reverseOrder());
        priority.addAll(List.of(2, 9, 4));
        PriorityQueue<Integer> priorityCopy = new PriorityQueue<>(priority);
        List<Integer> processingOrder = new ArrayList<>();
        while (!priorityCopy.isEmpty()) {
            processingOrder.add(priorityCopy.remove());
        }
        System.out.println("priorityProcessing=" + processingOrder);
        System.out.println("prioritySourceSize=" + priority.size());

        failsWith("dequeNull", NullPointerException.class,
                () -> new ArrayDeque<>(Arrays.asList("job", null)));

        ArrayBlockingQueue<String> bounded =
                new ArrayBlockingQueue<>(2, false, List.of("first", "second"));
        ArrayDeque<String> unboundedCopy = new ArrayDeque<>(bounded);
        System.out.println("boundedOffer=" + bounded.offer("third"));
        System.out.println("unboundedOffer=" + unboundedCopy.offerLast("third"));
        System.out.println("unboundedCopy=" + unboundedCopy);
    }

    public static void main(String[] args) {
        ownership();
        enumTarget();
        queueTarget();
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TargetCapabilitiesDemo.java
java TargetCapabilitiesDemo
```

Đầu ra:

```text
live=[alpha, beta]
snapshot=[alpha]
editable=[alpha, local]
snapshotAdd=UnsupportedOperationException
copyOfNull=NullPointerException
nullableSnapshot=[value, null]
enumInput=[WRITE, READ, WRITE]
enumTarget=[READ, WRITE]
enumEmptyList=IllegalArgumentException
enumExplicitEmpty=[]
enumEmptySetCopy=[]
priorityProcessing=[9, 4, 2]
prioritySourceSize=3
dequeNull=NullPointerException
boundedOffer=false
unboundedOffer=true
unboundedCopy=[first, second, third]
```

`live` nhìn thấy `beta` được thêm vào nguồn; `snapshot` vẫn giữ dãy ban đầu. Bản sao `editable` được phép thêm một phần tử riêng. Ba kết quả đáp ứng ba nhu cầu khác nhau.

`nullableSnapshot` cho thấy một kết quả không cho sửa cấu trúc vẫn có thể giữ `null` khi cách xây dựng được chọn có chủ ý. `List.copyOf` không đáp ứng chính sách phần tử ấy.

Đích enum chuyển `[WRITE, READ, WRITE]` thành `[READ, WRITE]`: vừa gộp trùng, vừa dùng thứ tự khai báo. Phần rỗng chứng minh khác biệt giữa collection thông thường rỗng và một `EnumSet` đã biết kiểu.

`priorityProcessing` được tạo bằng cách lấy hết từ bản sao hàng đợi ưu tiên, nên phản ánh thứ tự xử lý giảm dần. Nguồn vẫn có ba phần tử. Chương trình không dựa vào một dạng sắp xếp nội bộ của iterator.

Cuối cùng, cùng đang có hai công việc, hàng đợi giới hạn từ chối lần `offer` thứ ba còn bản sao `ArrayDeque` chấp nhận. Giữ hai phần tử ban đầu không bảo toàn chính sách dung lượng.

## 7. Dùng Stream vẫn phải chọn hợp đồng đích

### 7.1. Một phương thức thu thập không phải lời hứa về mọi lớp triển khai

Các cách sau không có cùng hợp đồng:

| Cách nhận kết quả | Cam kết cần hiểu |
| --- | --- |
| `collect(Collectors.toList())` | Trả một `List`, không bảo đảm lớp cụ thể, quyền sửa, khả năng tuần tự hóa hay an toàn nhiều luồng |
| `collect(Collectors.toSet())` | Trả một `Set`, không bảo đảm thứ tự hoặc lớp cụ thể |
| `stream.toList()` | List không cho sửa, giữ thứ tự gặp của luồng nếu luồng có thứ tự |
| `collect(Collectors.toCollection(factory))` | Chủ động chọn collection bằng hàm tạo được cung cấp |

Không ép kết quả `Collectors.toList()` thành `ArrayList` rồi coi một lớp triển khai đang quan sát được là hợp đồng API. Nếu cần chắc chắn có một `ArrayList` cho phép sửa, hãy yêu cầu nó qua hàm tạo.

Tương tự, `Collectors.toSet()` không phải cách diễn đạt yêu cầu giữ thứ tự gặp đầu tiên. Cần một đích có hợp đồng thích hợp như `LinkedHashSet`, đồng thời nguồn/luồng phải có thứ tự cần bảo toàn.

[`Collectors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html) nêu giới hạn của các bộ thu thập tổng quát; [`Stream.toList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()) cam kết kết quả không cho sửa.

### 7.2. Chọn hàm tạo khi cần quyền kiểm soát

Đoạn sau là phần thân minh họa, không phải chương trình chạy độc lập; cần các kiểu collection, `Comparator` và `Collectors` tương ứng:

```java
List<Integer> input = List.of(3, 1, 3, 2);

List<Integer> sequence = input.stream()
        .collect(Collectors.toCollection(ArrayList::new));

Set<Integer> firstEncounter = input.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

NavigableSet<Integer> descending = input.stream()
        .collect(Collectors.toCollection(
                () -> new TreeSet<Integer>(Comparator.reverseOrder())));
```

Ba kết quả lần lượt biểu diễn:

- `sequence`: `[3, 1, 3, 2]`, giữ mọi vị trí và thứ tự.
- `firstEncounter`: `[3, 1, 2]`, gộp giá trị trùng theo `equals` và giữ thứ tự gặp đầu.
- `descending`: `[3, 2, 1]`, gộp trùng và duy trì thứ tự giảm dần.

Hàm tạo phải cấp một collection mới, rỗng, phù hợp cho việc tích lũy kết quả. Không trả lại một đối tượng collection đang chứa dữ liệu dùng chung từ bên ngoài rồi trông chờ phép thu thập tự biến nó thành vùng làm việc độc lập.

Ví dụ dùng một luồng tuần tự xuất phát từ list có thứ tự. Nếu quy trình trước đó đã loại bỏ cam kết thứ tự, chọn `LinkedHashSet` ở cuối không tìm lại được thứ tự lịch sử đã mất.

### 7.3. Khi đích là Map, phải xác định chính sách khóa trùng

Chuyển các bản ghi thành map còn cần xác định khóa. Nếu hai bản ghi tạo ra cùng khóa, phải biết điều gì được phép xảy ra: báo lỗi, giữ bản ghi đầu, giữ bản ghi cuối, cộng gộp hay lưu một danh sách các bản ghi dưới khóa đó.

Dạng `Collectors.toMap(keyMapper, valueMapper)` báo `IllegalStateException` khi gặp khóa trùng theo hợp đồng của nó. Việc bổ sung một hàm hợp nhất là quyết định nghiệp vụ, không chỉ là cách làm cho ngoại lệ biến mất.

Đoạn minh họa sau chọn **giữ từ đầu tiên của mỗi độ dài** và dùng `LinkedHashMap` để giữ thứ tự xuất hiện của các khóa trong ví dụ:

```java
List<String> words = List.of("ax", "cat", "by");
Map<Integer, String> firstWordByLength = words.stream().collect(
        Collectors.toMap(
                String::length,
                Function.identity(),
                (first, later) -> first,
                LinkedHashMap::new));
```

Với dữ liệu đã cho, kết quả là `{2=ax, 3=cat}`. Từ `"by"` có cùng độ dài với `"ax"`, nên bị bỏ theo chính sách đã viết. Nếu mọi từ đều phải được giữ, chính sách này sai dù map được tạo thành công; cần một mô hình đích như `Map<Integer,List<String>>` hoặc một cấu trúc phù hợp khác.

Khi cần thứ tự khóa, chọn hàm tạo map có hợp đồng thứ tự tương ứng. Khi cần thứ tự sắp xếp, xác định thêm bộ so sánh và quy tắc nhận diện khóa. Không xem loại map, hàm tạo khóa và chính sách hợp nhất là ba quyết định độc lập về ý nghĩa dữ liệu.

## 8. Một quy trình chọn đích có thể kiểm tra được

### 8.1. Viết yêu cầu bằng các mệnh đề cụ thể

Thay cho yêu cầu mơ hồ “trả về bản sao collection”, có thể viết:

- Mọi dòng phải được giữ, kể cả các dòng có giá trị bằng nhau.
- Dãy kết quả đi theo thứ tự nhận vào.
- Phần tử `null` được chấp nhận hoặc bị từ chối theo chính sách đã nêu.
- Bên nhận không được thêm, xóa hoặc thay một phần tử của cấu trúc.
- Nguồn thay đổi cấu trúc về sau không làm kết quả thay đổi.
- Quyền sửa trạng thái của từng đối tượng phần tử được quy định riêng.

Với những yêu cầu này và nguồn có thứ tự, một bản `ArrayList` riêng được bọc bằng `unmodifiableList` có thể phù hợp. Chọn `Set` sẽ vi phạm yêu cầu giữ mọi dòng; chọn `List.copyOf` không phù hợp nếu bắt buộc giữ `null`; chỉ bọc trực tiếp nguồn không đáp ứng tính độc lập về cấu trúc.

Nếu yêu cầu thay thành “loại trùng, giữ lần gặp đầu”, đích khác có thể phù hợp. Khi sửa yêu cầu, cần xét lại cấu trúc đích thay vì thêm các phép ép kiểu để giữ nguyên một lựa chọn cũ.

### 8.2. Tách biến đổi dữ liệu khỏi chính sách chứa kết quả

Chuẩn hóa chữ hoa/thường, chuyển kiểu, loại `null`, gộp bản ghi hoặc lọc giá trị ngoài miền đều là những phép biến đổi có thể thay đổi ý nghĩa dữ liệu. Chúng phải được nêu rõ, không nên ẩn dưới một thao tác được gọi là “copy”.

Một luồng xử lý rõ ràng có thể là:

```text
Đầu vào
  -> xác thực điều kiện đầu vào
  -> biến đổi có chủ ý, nếu nghiệp vụ yêu cầu
  -> tích lũy vào cấu trúc đích được chọn
  -> áp dụng giới hạn/quyền sửa cần cung cấp
  -> công bố kết quả sau khi hoàn tất
```

Nếu xây dựng đích thất bại vì `null`, phần tử không so sánh được hoặc giới hạn dung lượng, không công bố một kết quả còn dở như thể đã đáp ứng đầy đủ hợp đồng. Khi thêm vào một collection đã tồn tại, cũng không mặc nhiên coi `addAll` là một giao dịch tự hoàn tác mọi thay đổi khi có ngoại lệ.

Việc xây dựng một kết quả riêng trước khi công bố giúp kiểm soát trạng thái mà bên nhận có thể quan sát. Nó không tự tạo tính nguyên tử cho các tác dụng phụ bên ngoài hoặc một nguồn đang bị sửa đồng thời.

### 8.3. Kiểm tra đúng các tính chất mà hợp đồng đã chọn

Chỉ kiểm tra `containsAll` là chưa đủ để chứng minh một phép chuyển đổi bảo toàn dãy. Phép kiểm tra ấy không thể hiện vị trí và không đếm đầy đủ số lần xuất hiện.

Có thể chọn các phép kiểm tra phù hợp hơn:

| Yêu cầu | Cách quan sát/kiểm tra phù hợp |
| --- | --- |
| Giữ toàn bộ dãy | So sánh các list theo đúng thứ tự và số lần xuất hiện |
| Giữ số lượng nhưng không cần thứ tự | So sánh tần suất theo quy tắc bằng nhau đã chọn |
| Giữ thứ tự duyệt của set | Quan sát một dãy được tạo từ iterator; `Set.equals` không kiểm tra thứ tự |
| Giữ quy tắc sắp xếp | Kiểm tra các giá trị đại diện và việc thêm phần tử mới, không chỉ ảnh chụp ban đầu |
| Giữ giới hạn khoảng | Thử một giá trị trong miền và một giá trị ngoài miền qua API được cung cấp |
| Giữ quyền chỉ đọc | Kiểm tra các đường sửa mà giao diện công bố |
| Giữ tính độc lập với nguồn | Sửa cấu trúc nguồn có kiểm soát và quan sát kết quả |
| Giữ thứ tự xử lý ưu tiên | Lấy dần từ một bản sao hàng đợi thay vì suy luận từ iterator |
| Giữ chính sách rỗng/null/dung lượng | Kiểm tra riêng những trường hợp biên này |

Không nên kiểm tra thứ tự của một lớp vốn không cam kết thứ tự rồi cố định kết quả của một lần chạy thành yêu cầu. Cũng không dùng tên lớp nội bộ hoặc một phép so sánh tham chiếu để thay cho kiểm tra hợp đồng của hàm tạo có quyền tái sử dụng kết quả.

### 8.4. Nguồn an toàn nhiều luồng không bảo đảm một bản chụp nguyên tử toàn cục

Một nguồn có thể cung cấp iterator với mức nhất quán phù hợp cho việc duyệt đồng thời, nhưng phép duyệt ấy không nhất thiết tương ứng với một ảnh chụp toàn bộ dữ liệu ở đúng một thời điểm.

Chọn một đích an toàn nhiều luồng giải quyết chính sách truy cập **đích**. Nó không tự tăng mức nhất quán của thao tác **đọc nguồn**. Nếu dữ liệu xuất ra phải phản ánh một trạng thái nghiệp vụ thống nhất, cần một giao thức phối hợp hoặc cơ chế ảnh chụp được nguồn hỗ trợ.

Ví dụ, [`ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) mô tả riêng hành vi của các thao tác tổng hợp và iterator trong lúc cập nhật đồng thời. Không suy từ việc từng thao tác của map an toàn nhiều luồng thành một cam kết “copy mọi mục là giao dịch nguyên tử”.

Một lần chạy không gặp ngoại lệ cũng không phải bằng chứng rằng các yêu cầu đồng thời đã được đáp ứng.

### 8.5. Xét chi phí sau khi đã chọn đúng ngữ nghĩa

Các cấu trúc có chi phí truy cập, cập nhật, sắp xếp và bộ nhớ khác nhau. Nhưng một đích nhanh hơn không phải thay thế hợp lệ nếu nó làm mất số lần xuất hiện, thứ tự hay khả năng mà API cần.

Nếu vừa cần giữ mọi dòng theo thứ tự vừa cần tra cứu nhanh một thông tin, có thể cần một list làm dữ liệu chính và một chỉ mục riêng. Khi đó phải có quy tắc cập nhật nhất quán giữa hai cấu trúc. Thay toàn bộ list bằng set không giải quyết được yêu cầu giữ đầy đủ các dòng.

Tương tự, tạo `TreeSet` chỉ để lấy một dãy sắp xếp có thể vừa tốn công duy trì cây, vừa làm mất phần tử trùng. Chọn list rồi sắp xếp có thể diễn đạt đúng nhu cầu hơn. Quyết định hiệu năng nên được đánh giá trên tập thao tác thật, sau khi các điều kiện bảo toàn dữ liệu đã được thỏa mãn.

## 9. Thực hành lựa chọn và giải thích

### Tình huống 1: Dãy giao dịch có các dòng bằng nhau

Đầu vào có hai giao dịch cùng giá trị nhưng chúng là hai lần phát sinh khác nhau. API cần giữ mọi dòng và thứ tự nhận vào.

**Phân tích:** không chuyển thành set chỉ vì hai dòng bằng nhau theo đối tượng hiện tại. Một list phù hợp hơn với ý nghĩa dãy. Nếu cần phân biệt danh tính nghiệp vụ, nên biểu diễn bằng mã giao dịch phù hợp, không dựa vào tình cờ hai đối tượng có địa chỉ khác nhau.

### Tình huống 2: Danh sách nhãn không trùng, giữ lần gặp đầu

Đầu vào là một list có thứ tự xác định, có nhãn lặp và cho phép một nhãn `null`. Người nhận chỉ cần đọc kết quả.

**Phân tích:** chọn chính sách gộp theo `equals`, tích lũy vào `LinkedHashSet`, rồi cung cấp lớp bọc không cho sửa nếu cần. `HashSet` không giữ cam kết thứ tự; `Set.copyOf` không đáp ứng chính sách `null` và không hứa giữ thứ tự gặp.

### Tình huống 3: Cần sắp xếp mọi dòng, không loại bản ghi

Đầu vào là các kết quả học tập, có nhiều bản ghi nhận cùng điểm. Muốn trả về dãy theo điểm nhưng vẫn giữ từng bản ghi.

**Phân tích:** một list được sắp xếp giữ được nhiều bản ghi có cùng khóa sắp xếp. Nếu dùng `TreeSet` với bộ so sánh chỉ theo điểm, những bản ghi so sánh bằng `0` có thể bị gộp. Nếu có yêu cầu thứ tự giữa các bản ghi cùng điểm, quy tắc phụ cũng cần được định nghĩa.

### Tình huống 4: API sao chép một tập hợp được sắp xếp giảm dần

Một phương thức nhận `Collection<Integer>` nhưng người gọi mong đích vẫn giảm dần và hỗ trợ truy vấn phạm vi.

**Phân tích:** hợp đồng đầu vào đang giấu thông tin cần thiết. Có thể yêu cầu `SortedSet`/`NavigableSet` phù hợp hoặc nhận bộ so sánh tường minh. Chọn `ArrayList` chỉ giữ dãy hiện tại; gọi hàm khởi tạo `TreeSet(Collection)` lại chọn thứ tự tự nhiên. Nếu còn phải giữ giới hạn của khung nhìn, cần áp dụng giới hạn riêng.

### Tình huống 5: Kết quả quyền truy cập enum có thể rỗng

Đầu vào là collection các quyền enum; có trường hợp không có quyền nào.

**Phân tích:** cung cấp kiểu enum tường minh để tạo đích rỗng, rồi thêm dữ liệu. Không dựa vào một phần tử đầu tiên vốn có thể không tồn tại. Xác định rõ rằng kết quả là tập hợp theo enum, không giữ lần lặp hay thứ tự tùy ý của đầu vào.

### Tình huống 6: Sao chép hàng đợi đang đầy để bàn giao xử lý

Nguồn có giới hạn dung lượng và dùng cơ chế chờ khi đầy/rỗng. Bên nhận còn tiếp tục thêm việc.

**Phân tích:** chỉ sao chép các phần tử vào `ArrayDeque` không giữ giới hạn hoặc cơ chế chờ. Phải chọn chính sách hàng đợi đích, dung lượng và giao thức bàn giao. Nếu chỉ cần một bản báo cáo các công việc hiện có, một list riêng lại có thể phù hợp vì không cần cam kết của hàng đợi vận hành.

Một lựa chọn đích có thể được giải thích rõ khi người viết chỉ ra được **điều gì được giữ, điều gì được thay đổi có chủ ý và thao tác tương lai nào chứng minh hợp đồng đó**.
