# Collectors.toList, toSet và toCollection

## 1. Ba bộ thu thập giải quyết vấn đề gì?

Một luồng `Stream` mô tả cách đọc và xử lý các phần tử. Sau khi lọc hoặc biến đổi, ứng dụng thường cần giữ kết quả để tiếp tục sử dụng: một dãy đầy đủ, một tập giá trị không trùng hoặc một loại collection có khả năng cụ thể.

Ba phương thức `Collectors.toList()`, `Collectors.toSet()` và `Collectors.toCollection(...)` tạo **bộ thu thập** (collector) cho công việc đó. Chúng chưa tạo ra danh sách dữ liệu ngay tại thời điểm được gọi; phương thức kết thúc `Stream.collect(...)` sử dụng bộ thu thập để tích lũy kết quả.

Cần phân biệt ba vai trò:

| Thành phần | Vai trò |
| --- | --- |
| `Stream<T>` | Luồng các phần tử và chuỗi thao tác xử lý |
| `Collector<T,A,R>` | Mô tả cách tích lũy phần tử để tạo kết quả |
| `Collectors` | Lớp tiện ích cung cấp các bộ thu thập thông dụng |

Trong `Collector<T,A,R>`:

- `T` là kiểu phần tử được nhận.
- `A` là kiểu của vùng tích lũy có thể thay đổi trong quá trình thu thập.
- `R` là kiểu kết quả được trả về.
- Dấu `?` trong các chữ ký tiện ích che giấu kiểu tích lũy nội bộ mà bên gọi không cần phụ thuộc vào.

Một luồng công việc điển hình:

```text
Nguồn dữ liệu
  -> Stream
  -> filter / map / các bước xử lý cần thiết
  -> collect(bộ thu thập)
  -> collection kết quả
```

Ví dụ, các lần xuất hiện lặp trong một dãy đơn hàng có thể đều phải được giữ, còn dãy nhãn dùng để lọc giao diện có thể chỉ cần mỗi nhãn một lần. Chọn bộ thu thập là chọn ý nghĩa của kết quả, không chỉ chọn cách viết ngắn hơn.

[API `Collector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html) mô tả quá trình tích lũy; [`Stream.collect`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector)) thực hiện phép thu thập đó.

### 1.1. Vì sao gọi toList riêng chưa có một List?

Đoạn sau minh họa các vai trò, không phải chương trình chạy độc lập:

```java
Collector<String, ?, List<String>> plan = Collectors.toList();
List<String> result = Stream.of("sun", "rain").collect(plan);
```

`plan` là kế hoạch thu thập. `result` mới là danh sách chứa dữ liệu sau khi thao tác kết thúc chạy.

Hai cách viết dưới đây không biên dịch; chúng là các ví dụ lỗi cần phân biệt:

```java
List<String> wrong = Collectors.toList();

Stream.of("x").collect(
        Collectors.toCollection(new ArrayList<String>()));
```

Dòng đầu nhầm bộ thu thập với kết quả. Dòng sau truyền một đối tượng collection, trong khi `toCollection` cần một hàm tạo có kiểu `Supplier`. Cách đúng thường dùng tham chiếu hàm tạo như `ArrayList::new` hoặc lambda tạo đối tượng mới.

## 2. Đọc hợp đồng của ba phương thức

Các chữ ký API rút gọn:

```java
static <T> Collector<T, ?, List<T>> toList();
static <T> Collector<T, ?, Set<T>> toSet();
static <T, C extends Collection<T>>
        Collector<T, ?, C> toCollection(Supplier<C> collectionFactory);
```

| Phương thức | Kết quả | Phần tử trùng | Thứ tự | Quyền kiểm soát lớp đích |
| --- | --- | --- | --- | --- |
| `Collectors.toList()` | `List<T>` | Giữ các lần xuất hiện | Giữ thứ tự gặp của luồng nếu có | Không hứa lớp triển khai cụ thể |
| `Collectors.toSet()` | `Set<T>` | Gộp theo hợp đồng set | Không cam kết giữ thứ tự gặp | Không hứa lớp triển khai cụ thể |
| `Collectors.toCollection(factory)` | `C` do hàm tạo chọn | Theo collection được tạo | Tích lũy theo thứ tự gặp; cách duyệt còn phụ thuộc loại đích | Chọn tường minh qua hàm tạo |

Hai bộ thu thập tổng quát `toList` và `toSet` không cam kết lớp triển khai, khả năng sửa, khả năng tuần tự hóa hoặc tính an toàn khi nhiều luồng dùng kết quả.

Do đó, không nên ép kết quả `toList` thành `ArrayList`, cũng không nên coi `toSet` là lời hứa sẽ trả `HashSet`. Một cách triển khai có thể sử dụng những lớp đó mà không biến tên lớp đang quan sát được thành hợp đồng công khai.

Nếu cần chắc chắn một `ArrayList` có thể thêm/xóa phần tử, yêu cầu nó qua `toCollection(ArrayList::new)`. Nếu cần kết quả chỉ đọc, phải chọn một API hoặc bước hoàn tất có cam kết tương ứng; không suy ra cả quyền sửa lẫn việc cấm sửa chỉ từ tên `toList`.

[Đặc tả `Collectors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html) nêu rõ giới hạn của hai bộ thu thập tổng quát và vai trò của `toCollection`.

### 2.1. Thứ tự gặp không phải thứ tự các luồng con chạy xong

**Thứ tự gặp** (encounter order) là thứ tự mà nguồn/chuỗi thao tác cung cấp cho các phần tử. List thường cung cấp thứ tự dãy; một nguồn không có cam kết thứ tự không tự trở thành có thứ tự chỉ vì kết quả được đưa vào list.

Một phép thu thập bảo toàn thứ tự gặp có thể chạy song song mà vẫn trả kết quả theo thứ tự ấy. Điều đó không yêu cầu từng luồng xử lý phải kết thúc theo thứ tự từ phần tử đầu tới cuối.

`toSet` là bộ thu thập có đặc tính `UNORDERED`: nó không cam kết giữ thứ tự gặp. Điều này không có nghĩa nó phải xáo ngẫu nhiên phần tử hoặc phải tạo một thứ tự khác ở mỗi lần chạy. Một đầu ra tình cờ có vẻ đã sắp xếp không bổ sung cam kết thứ tự cho API.

### 2.2. sorted rồi toSet không bảo đảm duyệt theo thứ tự đã sắp xếp

Nếu ứng dụng sắp xếp luồng rồi kết thúc bằng `toSet`, hợp đồng của đích vẫn không hứa thứ tự duyệt tương ứng.

Tùy yêu cầu, có thể chọn:

- `sorted(...).collect(Collectors.toList())` để giữ một dãy đã sắp xếp, gồm cả những lần xuất hiện lặp.
- `collect(Collectors.toCollection(TreeSet::new))` để có một tập hợp duy trì thứ tự tự nhiên và gộp các phần tử theo quy tắc so sánh.
- `collect(Collectors.toCollection(LinkedHashSet::new))` để gộp trùng nhưng giữ thứ tự chèn theo nguồn có thứ tự.

Đây là ba ý định khác nhau. Dùng `TreeSet` chỉ để “làm list có thứ tự” có thể làm mất các lần xuất hiện mà nghiệp vụ còn cần.

## 3. Chương trình 1: Dãy đầy đủ, tập hợp và đích tường minh

Chương trình này cố ý không in một thứ tự cụ thể cho kết quả `toSet`. Nó kiểm tra nội dung tập hợp bằng `Set.equals` và kiểm tra số phần tử, vì đó mới là những điều cần quan sát.

Tệp `BasicCollectionCollectorsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.LinkedHashSet;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BasicCollectionCollectorsDemo {
    public static void main(String[] args) {
        List<String> drinks =
                new ArrayList<>(List.of("tea", "coffee", "tea", "juice"));

        List<String> all = drinks.stream().collect(Collectors.toList());
        Set<String> unique = drinks.stream().collect(Collectors.toSet());
        ArrayList<String> editable = drinks.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        LinkedHashSet<String> firstSeen = drinks.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        TreeSet<String> sortedUnique = drinks.stream()
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("all=" + all);
        System.out.println("uniqueSize=" + unique.size());
        System.out.println("uniqueValues=" +
                unique.equals(Set.of("tea", "coffee", "juice")));
        System.out.println("firstSeen=" + firstSeen);
        System.out.println("sortedUnique=" + sortedUnique);

        editable.add("water");
        drinks.add("cocoa");
        System.out.println("editable=" + editable);
        System.out.println("sourceNow=" + drinks);
        System.out.println("allStill=" + all);

        System.out.println("emptyList=" +
                Stream.<String>empty().collect(Collectors.toList()).isEmpty());
        System.out.println("emptySet=" +
                Stream.<String>empty().collect(Collectors.toSet()).isEmpty());

        List<String> nullable = Stream.of("milk", null, "milk")
                .collect(Collectors.toList());
        Set<String> nullableSet = Stream.of("milk", null, "milk")
                .collect(Collectors.toSet());
        System.out.println("nullableList=" + nullable);
        System.out.println("nullableSetSize=" + nullableSet.size());
        System.out.println("nullableSetContainsNull=" + nullableSet.contains(null));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK hỗ trợ Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 BasicCollectionCollectorsDemo.java
java BasicCollectionCollectorsDemo
```

Đầu ra:

```text
all=[tea, coffee, tea, juice]
uniqueSize=3
uniqueValues=true
firstSeen=[tea, coffee, juice]
sortedUnique=[coffee, juice, tea]
editable=[tea, coffee, tea, juice, water]
sourceNow=[tea, coffee, tea, juice, cocoa]
allStill=[tea, coffee, tea, juice]
emptyList=true
emptySet=true
nullableList=[milk, null, milk]
nullableSetSize=2
nullableSetContainsNull=true
```

### 3.1. Các kết quả khác nhau vì hợp đồng khác nhau

`all` giữ hai lần `"tea"`. `uniqueSize=3` cho thấy tập hợp đã gộp trùng; `uniqueValues=true` xác nhận đủ ba giá trị cần có mà không phụ thuộc thứ tự duyệt.

`firstSeen` giữ thứ tự xuất hiện đầu tiên của mỗi giá trị trong luồng tuần tự này nhờ `LinkedHashSet`. `sortedUnique` lại duyệt theo thứ tự tự nhiên của `TreeSet`.

`editable` có lớp đích được yêu cầu tường minh là `ArrayList`, nên lời gọi `add("water")` thuộc hợp đồng của lớp đó. Chương trình không dùng một lời gọi sửa trên kết quả `Collectors.toList()` để biến hành vi của một bản JDK thành điều kiện bắt buộc của API.

Khi thêm `"cocoa"` vào nguồn sau thu thập, `all` vẫn giữ dãy đã tích lũy. Kết quả không phải khung nhìn sống của list nguồn. Các đối tượng phần tử bên trong vẫn có thể được chia sẻ; chương trình thứ ba sẽ kiểm tra riêng điều đó.

### 3.2. Luồng rỗng và phần tử null

Luồng rỗng vẫn được thu thập thành kết quả rỗng; không cần tự rẽ nhánh trả `null` để biểu diễn “không có phần tử”.

Hai kết quả cuối có `null` chứng minh hành vi của cách triển khai đang chạy ví dụ. Trong mã nguồn OpenJDK 17, `toList` dùng `ArrayList` và `toSet` dùng `HashSet` để tích lũy. Đây là thông tin về cách triển khai, không phải lời hứa rằng kết quả luôn có chính các lớp ấy.

Nếu chính sách `null` là phần bắt buộc của hợp đồng ứng dụng, hãy xác thực rõ ràng hoặc chọn một loại đích có chính sách đã biết qua `toCollection`. Không dùng một bộ thu thập tổng quát như thể nó tự thực hiện quy tắc nghiệp vụ “loại mọi phần tử null”.

[Mã nguồn `Collectors` của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/stream/Collectors.java) hữu ích để giải thích các quan sát; mã ứng dụng vẫn nên dựa trên hợp đồng công khai hoặc đích đã chọn tường minh.

## 4. toCollection: cung cấp một hàm tạo đúng hợp đồng

### 4.1. Hàm tạo phải tạo collection mới và rỗng

`Supplier<C>` là giao diện hàm không nhận đối số và trả về một `C` khi gọi `get()`. Riêng hợp đồng `toCollection` yêu cầu hàm được cung cấp trả về **một collection mới, rỗng** để tích lũy dữ liệu.

Điểm phân biệt này quan trọng: giao diện [`Supplier`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html) nói chung không bắt buộc mọi lời gọi phải tạo một đối tượng khác. Yêu cầu mới/rỗng ở đây đến từ ngữ cảnh [`Collectors.toCollection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)), không phải từ tên `Supplier` đứng riêng.

Có thể diễn đạt hai cách tạo tương đương:

```java
// Doan minh hoa ham tao, khong phai chuong trinh doc lap.
Collectors.toCollection(ArrayList::new);
Collectors.toCollection(() -> new ArrayList<String>());
```

Vì cần tích lũy phần tử và ghép các kết quả trung gian, collection được tạo phải hỗ trợ các thao tác cần thiết. Trả về một collection không cho thêm phần tử không đáp ứng vai trò đó, dù đối tượng ấy triển khai giao diện `Collection`.

Không nên trả về một biến collection dùng chung, kể cả khi nó đang rỗng ở lần gọi đầu tiên. Lần thu thập khác có thể nhận lại chính dữ liệu đã tích lũy; khi chạy song song, các vùng đáng lẽ độc lập còn có thể cùng trỏ tới một đối tượng.

### 4.2. Hàm tạo có thể mang cấu hình của loại đích

Khi cần một bộ so sánh, lambda có thể cung cấp cấu hình cho từng collection mới:

```java
// Doan minh hoa: order la Comparator<String> da duoc xac dinh.
Collectors.toCollection(() -> new TreeSet<String>(order));
```

Các collection riêng có thể dùng cùng một bộ so sánh ổn định. Điều cần tránh là dùng chung chính bộ chứa kết quả hoặc để quy tắc so sánh thay đổi trong lúc thu thập.

Loại đích còn quyết định ý nghĩa của thao tác thêm:

- `ArrayList` giữ các lần xuất hiện và thứ tự thêm.
- `LinkedHashSet` gộp trùng theo `equals/hashCode`, giữ thứ tự chèn.
- `TreeSet` xác định trùng theo kết quả so sánh bằng `0`, đồng thời duy trì thứ tự so sánh.
- Một loại khác có thể có chính sách `null` hoặc giới hạn riêng.

Vì vậy, `toCollection` tích lũy theo thứ tự gặp không có nghĩa iterator của mọi loại đích sẽ duyệt theo thứ tự ấy. Ví dụ, `TreeSet` thể hiện thứ tự của bộ so sánh khi duyệt. Nếu chọn một tập hợp không cam kết thứ tự duyệt, hàm thu thập không biến nó thành tập hợp có thứ tự.

[`LinkedHashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) và [`TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html) có hợp đồng rất khác nhau. Với `TreeSet`, bộ so sánh cần nhất quán với `equals` để tuân thủ hợp đồng chung của `Set`; so sánh chỉ theo một thuộc tính không đủ phân biệt bản ghi có thể làm gộp dữ liệu ngoài ý muốn.

### 4.3. Có thể dùng lại collector, nhưng không dùng chung vùng tích lũy

Một collector được cấu hình đúng có thể được dùng cho các luồng độc lập. Mỗi lần thu thập sẽ nhận collection riêng từ hàm tạo.

Đây là hai mức khác nhau:

- Dùng lại mô tả cách thu thập.
- Dùng lại cùng một collection đang chứa kết quả của lần trước.

Mức đầu hữu ích để đóng gói chính sách. Mức sau vi phạm yêu cầu của hàm tạo trong `toCollection`.

Cũng cần phân biệt collector với `Stream`: một đối tượng stream chỉ được sử dụng cho một lần duyệt/chuỗi thao tác kết thúc theo hợp đồng. Muốn thu cùng nguồn thành list rồi thành set, hãy tạo những stream riêng từ nguồn, như chương trình thứ nhất đã làm.

### 4.4. Chương trình 2: Hàm tạo đúng, hàm tạo sai và cấu hình TreeSet

Phần `invalidPlan` cố ý minh họa cách dùng sai bằng dữ liệu cục bộ và các lần thu thập tuần tự. Nó không phải mẫu để dùng trong ứng dụng.

Tệp `CollectorFactoryContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorFactoryContractDemo {
    public static void main(String[] args) {
        Collector<String, ?, LinkedHashSet<String>> plan =
                Collectors.toCollection(LinkedHashSet::new);
        LinkedHashSet<String> first = Stream.of("blue", "red", "blue").collect(plan);
        LinkedHashSet<String> second = Stream.of("green").collect(plan);
        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("sameResult=" + (first == second));

        Comparator<String> order =
                Comparator.nullsFirst(Comparator.reverseOrder());
        TreeSet<String> custom = Stream.of("tea", null, "juice", "coffee", "tea")
                .collect(Collectors.toCollection(() -> new TreeSet<>(order)));
        System.out.println("customOrder=" + custom);

        try {
            Stream.of("one", null)
                    .collect(Collectors.toCollection(TreeSet::new));
            throw new AssertionError("Natural-order tree accepted null");
        } catch (NullPointerException expected) {
            System.out.println("naturalNull=NullPointerException");
        }

        try {
            Stream.of("one")
                    .collect(Collectors.toCollection(() -> List.<String>of()));
            throw new AssertionError("Read-only accumulator accepted data");
        } catch (UnsupportedOperationException expected) {
            System.out.println("readOnlyFactory=UnsupportedOperationException");
        }

        ArrayList<String> shared = new ArrayList<>();
        Collector<String, ?, ArrayList<String>> invalidPlan =
                Collectors.toCollection(() -> shared);
        ArrayList<String> badFirst = Stream.of("first").collect(invalidPlan);
        ArrayList<String> badSecond = Stream.of("second").collect(invalidPlan);
        ArrayList<String> badEmpty = Stream.<String>empty().collect(invalidPlan);
        System.out.println("badSameResult=" + (badFirst == badSecond));
        System.out.println("badFirstNow=" + badFirst);
        System.out.println("badEmpty=" + badEmpty);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CollectorFactoryContractDemo.java
java CollectorFactoryContractDemo
```

Đầu ra:

```text
first=[blue, red]
second=[green]
sameResult=false
customOrder=[null, tea, juice, coffee]
naturalNull=NullPointerException
readOnlyFactory=UnsupportedOperationException
badSameResult=true
badFirstNow=[first, second]
badEmpty=[first, second]
```

`sameResult=false` xác nhận collector đúng tạo kết quả riêng cho hai lần thu thập. Kết quả đầu không bị bổ sung phần tử của lần sau.

`customOrder` là set dùng bộ so sánh xử lý `null` trước, sau đó đảo thứ tự tự nhiên. Trong khi đó, cây dùng thứ tự tự nhiên không chấp nhận phần tử `null`. Chính sách này đến từ loại đích và bộ so sánh, không phải vì `toCollection` tự lọc dữ liệu.

`readOnlyFactory` thất bại khi cần thêm phần tử vào list được tạo bằng `List.of`. Một đầu vào rỗng có thể không làm lộ vấn đề thêm phần tử, nên thử thành công với dữ liệu rỗng chưa chứng minh hàm tạo phù hợp cho mọi đầu vào.

Ba dòng cuối cho thấy lỗi dùng chung collection rất rõ: kết quả cũ thay đổi sau lần thu thập mới, và thu một stream rỗng lại trả collection đang có dữ liệu. Không cần chờ một lỗi song song ngẫu nhiên để nhận ra hàm tạo đã sai hợp đồng.

## 5. Thu thập song song và bộ chứa kết quả

### 5.1. Vì sao có thể dùng ArrayList trong một phép collect song song?

Một bộ thu thập có thể mô tả bốn phần phối hợp:

| Thành phần | Vai trò |
| --- | --- |
| Hàm cấp bộ chứa, `supplier` | Tạo vùng tích lũy ban đầu |
| Hàm tích lũy, `accumulator` | Đưa một phần tử vào vùng tích lũy |
| Hàm ghép, `combiner` | Kết hợp các kết quả trung gian |
| Bước hoàn tất, `finisher` | Chuyển vùng tích lũy thành kết quả cuối nếu cần |

Với cách thu thập không dùng chung một bộ chứa giữa các luồng tích lũy, thư viện có thể chia dữ liệu thành các phần, tạo vùng riêng cho từng phần, rồi ghép sau khi tích lũy hoàn tất. Bản thân mỗi `ArrayList` riêng không cần chịu các lời gọi thêm đồng thời từ nhiều luồng.

[Hợp đồng `Collector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html) quy định việc cô lập vùng tích lũy đối với các collector không đồng thời. Đây là nền tảng để dùng phép thu thập song song đúng cách.

Điều đó không trao quyền chia sẻ cùng một `ArrayList` ra ngoài rồi để nhiều luồng tự sửa nó. Cũng không biến list cuối cùng thành một cấu trúc an toàn cho mọi truy cập đồng thời sau khi trả về.

### 5.2. Parallel không đồng nghĩa với CONCURRENT

Đặc tính `Collector.Characteristics.CONCURRENT` có nghĩa hàm tích lũy có thể được gọi đồng thời trên **cùng một bộ chứa kết quả**. Đây là cam kết khác với khả năng thư viện thực hiện nhiều phần tích lũy độc lập song song.

Một collection đích có cơ chế an toàn nhiều luồng cũng không tự thay thế được việc đọc các đặc tính của collector. Trong cách triển khai OpenJDK 17, `toCollection` không tự trở thành collector có `CONCURRENT` chỉ vì hàm tạo được cung cấp trả về một hàng đợi an toàn nhiều luồng.

`UNORDERED` lại là một đặc tính khác, nói về việc không cam kết giữ thứ tự gặp. Không được suy ra `UNORDERED` có nghĩa cho phép nhiều luồng tùy ý sửa cùng một bộ chứa.

[`Collector.Characteristics`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.Characteristics.html) định nghĩa các thuộc tính này. Khi phân tích một cách triển khai cụ thể, có thể quan sát `characteristics()`; không suy từ tên lớp đích thành một đặc tính mà collector chưa công bố.

### 5.3. Giữ thứ tự đầu vào không yêu cầu thứ tự thực thi cố định

Một luồng có thứ tự có thể xử lý các phần ở thời điểm khác nhau rồi ghép kết quả đúng thứ tự gặp. Vì vậy, `parallel().collect(Collectors.toList())` không mặc nhiên đảo lộn thứ tự list.

Nguồn và các thao tác trước đó vẫn phải cung cấp cam kết thứ tự cần giữ. Một nguồn không có thứ tự, hoặc một bước chủ ý bỏ cam kết thứ tự, không được bộ thu thập tự khôi phục lịch sử.

Không thay phép thu thập bằng một tác dụng phụ vào collection bên ngoài như đoạn cần tránh sau:

```java
// Mau can tranh: shared khong phai vung tich luy rieng cua collector.
List<String> shared = new ArrayList<>();
source.parallelStream().forEach(shared::add);
```

Đoạn trên có nguy cơ tranh chấp khi nhiều luồng thêm vào cùng list; nó cũng không cung cấp cơ chế ghép theo thứ tự của một phép thu thập. Chạy thành công một lần không chứng minh cách viết đó đúng. Sử dụng `collect` với bộ thu thập phù hợp để thư viện quản lý các vùng tích lũy.

### 5.4. Chương trình 3: Kết quả song song, quyền sửa và tham chiếu phần tử

Tệp `ParallelCollectorDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelCollectorDemo {
    public static void main(String[] args) {
        List<Integer> sequential = IntStream.range(0, 5000)
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toList());
        List<Integer> parallel = IntStream.range(0, 5000)
                .parallel()
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toList());
        System.out.println("sameOrderedList=" + sequential.equals(parallel));
        System.out.println("parallelSize=" + parallel.size());

        Set<Integer> unique = IntStream.range(0, 5000)
                .parallel()
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toSet());
        LinkedHashSet<Integer> orderedUnique = IntStream.range(0, 5000)
                .parallel()
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        System.out.println("parallelSetSize=" + unique.size());
        System.out.println("parallelFirstSeen=" + orderedUnique);

        Collector<Integer, ?, ConcurrentLinkedQueue<Integer>> queueCollector =
                Collectors.toCollection(ConcurrentLinkedQueue::new);
        System.out.println("queueCollectorConcurrent=" +
                queueCollector.characteristics()
                        .contains(Collector.Characteristics.CONCURRENT));

        List<Integer> directList = IntStream.range(0, 3).boxed().toList();
        System.out.println("streamToList=" + directList);
        try {
            directList.add(99);
            throw new AssertionError("Stream.toList result was editable");
        } catch (UnsupportedOperationException expected) {
            System.out.println("streamToListAdd=UnsupportedOperationException");
        }

        List<Integer> editable = IntStream.range(0, 3).boxed()
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add(99);
        System.out.println("explicitEditable=" + editable);

        StringBuilder message = new StringBuilder("status");
        List<StringBuilder> collected = Stream.of(message)
                .collect(Collectors.toList());
        message.append("-updated");
        System.out.println("sameElement=" + (collected.get(0) == message));
        System.out.println("elementAfter=" + collected);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ParallelCollectorDemo.java
java ParallelCollectorDemo
```

Đầu ra:

```text
sameOrderedList=true
parallelSize=5000
parallelSetSize=13
parallelFirstSeen=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
queueCollectorConcurrent=false
streamToList=[0, 1, 2]
streamToListAdd=UnsupportedOperationException
explicitEditable=[0, 1, 2, 99]
sameElement=true
elementAfter=[status-updated]
```

`sameOrderedList=true` kiểm tra cả thứ tự và số lần xuất hiện của 5.000 phần tử. `parallelSetSize=13` kiểm tra kết quả gộp các giá trị từ `0` tới `12`. `parallelFirstSeen` còn giữ thứ tự gặp đầu tiên qua một đích `LinkedHashSet`.

`queueCollectorConcurrent=false` là quan sát đặc tính của collector được tạo trong ví dụ. Điểm cần hiểu là collection đích và cơ chế tích lũy của collector có các cam kết riêng; chọn một hàng đợi an toàn nhiều luồng không làm mọi kiểu phép thu thập trở thành tích lũy đồng thời vào cùng một vùng.

Phần `streamToListAdd` sẽ được đối chiếu với `Collectors.toList` ở phần tiếp theo. Phần `sameElement` và `elementAfter` cho thấy một giới hạn khác: tạo collection kết quả mới không tự sao chép sâu những đối tượng phần tử.

## 6. Quyền sửa là một hợp đồng riêng của kết quả

Trong ví dụ Collector ở mục 3–5, `Collectors.toList()` tạo một `List` nhưng **không cam kết khả năng sửa hoặc lớp triển khai cụ thể**. `Collectors.toCollection(ArrayList::new)` chủ động chọn `ArrayList` có thể thêm, xóa và thay phần tử. Còn `Stream.toList()` (Java 16+) là một terminal trực tiếp, có cam kết kết quả **không cho sửa**. Ba cách viết này không tương đương chỉ vì đều tạo `List`.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Thu các phần tử thành List nhưng không cần lớp cụ thể | `collect(Collectors.toList())` |
| Thu thành List có quyền thêm hoặc sửa được xác định rõ | `collect(Collectors.toCollection(ArrayList::new))` |
| Chỉ cần danh sách kết quả không cho sửa, vẫn có thể chứa null | `stream.toList()` |
| Cần kết quả không cho sửa và từ chối null | `collect(Collectors.toUnmodifiableList())` |

Cũng có thể tích lũy vào một `ArrayList` mới rồi dùng `collectingAndThen` với `Collections.unmodifiableList` để trả một lớp bao chỉ đọc. Không được dùng chính lớp bao chỉ đọc làm vùng tích lũy của `toCollection`, vì hàm tích lũy vẫn cần thêm phần tử. Trường hợp collector chạy song song, thư viện có thể tạo nhiều vùng chứa rồi ghép; kết quả cuối không tự trở thành an toàn cho mọi thao tác sửa đồng thời về sau.

Riêng các đối tượng phần tử vẫn có thể dùng chung tham chiếu với nguồn. Ví dụ `StringBuilder` trong chương trình 3 thay đổi trạng thái mà không cần thay vị trí của List. Khi cần ảnh chụp độc lập ở cấp dữ liệu, phải tạo phần tử mới phù hợp. Bài *Stream.toList, collect và giới hạn bảo đảm về khả năng sửa* phân tích chi tiết phép `set`, `sort`, chính sách null, chuyển đổi kiểu và các giới hạn này.

## 7. Chọn và sử dụng bộ thu thập theo yêu cầu cụ thể

### 7.1. Bảng lựa chọn nhanh

| Yêu cầu | Lựa chọn phù hợp |
| --- | --- |
| Giữ mọi lần xuất hiện, cần một `List`, chưa yêu cầu lớp cụ thể | `Collectors.toList()` |
| Chỉ cần tập giá trị không trùng, không yêu cầu thứ tự hay lớp cụ thể | `Collectors.toSet()` |
| Chắc chắn cần list cho phép sửa theo hợp đồng `ArrayList` | `Collectors.toCollection(ArrayList::new)` |
| Gộp trùng và giữ thứ tự gặp của một nguồn có thứ tự | `Collectors.toCollection(LinkedHashSet::new)` |
| Cần một tập hợp duy trì bộ so sánh riêng | `toCollection` với hàm tạo một `TreeSet` mới có bộ so sánh ấy |
| Cần kết quả chỉ đọc | Chọn API/bước hoàn tất có cam kết chỉ đọc và đúng chính sách `null` |
| Cần giữ dữ liệu lặp rồi sắp xếp | Giữ kiểu dãy và dùng quy tắc sắp xếp; không tự thay bằng set |

Một yêu cầu như “không trùng” cần gắn với quy tắc nhận diện. Với set băm thông thường, cần `equals/hashCode` đúng hợp đồng. Với cây, phép so sánh bằng `0` quyết định việc gộp. Không thể đổi loại set rồi giả định mọi kiểu phần tử vẫn có cùng ý nghĩa trùng.

Nếu các đối tượng bằng nhau theo `equals` nhưng còn có trạng thái khác, `toSet` không cung cấp một chính sách nghiệp vụ “luôn giữ đúng bản ghi đầu tiên” để lựa chọn trạng thái đại diện. Hãy xác định chính sách đó rõ ràng và dùng một quy trình có cam kết phù hợp.

### 7.2. Phân biệt lọc dữ liệu với cách chứa dữ liệu

Chọn `ArrayList` hoặc `TreeSet` không thay thế việc xác thực đầu vào. Các câu hỏi cần được định nghĩa riêng:

- `null` là dữ liệu hợp lệ, cần bị loại bỏ hay phải làm cả thao tác thất bại?
- Các lần xuất hiện có ý nghĩa riêng hay được phép gộp?
- Cần giữ thứ tự nhận vào, thứ tự sắp xếp hay không cần thứ tự?
- Kiểu đích có thể chứa và so sánh được mọi giá trị nhận vào không?

Nếu nghiệp vụ chọn bỏ phần tử `null`, hãy làm bước lọc tường minh. Nếu nghiệp vụ chọn từ chối dữ liệu thiếu, đó là một quy tắc khác. Không gọi chung hai hành vi này là “làm sạch” rồi để loại collection tình cờ quyết định.

Tương tự, `toSet` không đếm tần suất. Sau khi các lần xuất hiện bằng nhau bị gộp, không thể chỉ từ set mà suy ra mỗi giá trị đã xuất hiện bao nhiêu lần.

### 7.3. Cẩn thận với stream và trạng thái bên ngoài

Hàm tạo, hàm biến đổi và các quy tắc được sử dụng trong quá trình thu thập cần đáp ứng hợp đồng tương ứng. Không sửa nguồn trong lúc stream đang duyệt nó, cũng không dùng một collection bên ngoài làm nơi chứa chung thay cho vùng tích lũy được thư viện quản lý.

Một nguồn là `ArrayList` thông thường có thể được đọc bởi một stream song song khi được dùng đúng điều kiện, không bị sửa trong lúc duyệt. Không cần biến mọi nguồn thành cấu trúc đồng thời chỉ vì xuất hiện `parallel()`. Điều phải kiểm soát là cách nguồn được truy cập và cách vùng tích lũy được quản lý.

Sau khi thu thập, nếu kết quả được trao cho nhiều luồng cùng sửa, cần một chính sách truy cập phù hợp cho kết quả ấy. Thành công của phép `collect` song song không chứng minh list trả về tự có mọi đặc tính an toàn đồng thời cho phần còn lại của ứng dụng.

[Hợp đồng `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html) yêu cầu các hàm xử lý không can thiệp vào nguồn và giải thích việc sử dụng một stream theo một lần duyệt.

### 7.4. Chi phí vật chất hóa kết quả

Các bộ thu thập này tạo collection chứa kết quả, không tạo một khung nhìn lười tiếp tục đọc nguồn về sau. Với một list giữ `n` phần tử, cần chỗ cho các tham chiếu tương ứng. Với set, số giá trị được giữ còn phụ thuộc số phần tử phân biệt và chính sách của đích.

Một luồng kết quả vô hạn không thể được thu đầy đủ vào một collection hữu hạn. Cần thiết kế giới hạn hoặc cơ chế tiêu thụ phù hợp thay vì dùng `collect` như một thao tác tự dừng.

Chạy song song còn có chi phí tạo các vùng riêng và ghép kết quả. `parallel()` không tự bảo đảm nhanh hơn. Cấp trước một dung lượng rất lớn trong hàm tạo của `toCollection` cũng có thể gây lãng phí nếu hàm ấy được gọi cho nhiều phần dữ liệu.

Không dựa vào giả định “hàm tạo chỉ được gọi đúng một lần” để tính dung lượng, ghi nhận nghiệp vụ hoặc chia sẻ một bộ đệm. Khi hiệu năng quan trọng, cần đo trên dữ liệu và chuỗi thao tác thực sự, đồng thời giữ đúng hợp đồng của hàm tạo.

### 7.5. Kiểm tra kết quả bằng đúng tính chất được cam kết

Khi kiểm tra một phép thu thập:

- Với list có thứ tự, kiểm tra cả dãy và số lần xuất hiện.
- Với `toSet`, kiểm tra tập giá trị; không cố định một thứ tự mà API không hứa.
- Với đích tường minh, kiểm tra những khả năng mà kiểu đích cần cung cấp.
- Kiểm tra đầu vào rỗng, dữ liệu lặp và chính sách `null` theo yêu cầu.
- Nếu dùng lại collector, xác nhận kết quả giữa các lần thu thập không bị dùng chung ngoài ý muốn.
- Nếu dùng song song, so sánh kết quả theo đúng hợp đồng, không theo thứ tự các tác vụ hoàn tất.

Không dùng một phép ép kiểu, tên lớp nội bộ hoặc một lần sửa thành công trên một JDK để thay cho cam kết mà API đã công bố.

## 8. Thực hành và giải thích

### Bài 1: Một list có phần tử lặp cần giữ nguyên

Cho một nguồn có thứ tự `[tea, coffee, tea, juice]`. Cần lấy ra một list giữ đủ bốn vị trí và còn phải thêm phần tử về sau.

**Điểm cần giải thích:** giữ kiểu dãy đáp ứng yêu cầu số lần xuất hiện; chọn `toCollection(ArrayList::new)` diễn đạt thêm quyền sửa. `toSet` làm mất một lần `tea`; `Collectors.toList` không đủ để cam kết một lớp có quyền sửa cụ thể.

### Bài 2: Nhãn không trùng, giữ thứ tự gặp

Cho luồng có thứ tự, cần gộp các nhãn bằng nhau theo `equals` và giữ thứ tự xuất hiện đầu tiên.

**Điểm cần giải thích:** `toCollection(LinkedHashSet::new)` cung cấp một đích có hợp đồng phù hợp. `toSet` không cam kết thứ tự. Nếu nguồn đã không còn thứ tự cần thiết, chọn lớp đích có thứ tự cũng không khôi phục được lịch sử đã mất.

### Bài 3: Hàm tạo trả về một biến collection dùng chung

Một hàm tạo trả về biến `shared`. Để “sửa”, người viết gọi `clear()` trên nó trước mỗi lần trả về.

**Điểm cần giải thích:** xóa dữ liệu không tạo ra đối tượng riêng. Các lần thu thập vẫn có thể giữ cùng một collection; khi có nhiều vùng tích lũy, một lần xóa còn có thể phá dữ liệu vùng khác. Cần cấp collection mới, rỗng theo đúng hợp đồng thay vì tái sử dụng đối tượng dùng chung.

### Bài 4: Dùng collection chỉ đọc làm vùng tích lũy

Một đầu vào rỗng chạy qua `toCollection(() -> List.of())` có vẻ không gặp lỗi. Sau đó cùng mã thất bại với đầu vào có phần tử.

**Điểm cần giải thích:** trường hợp rỗng chưa thực hiện đường thêm dữ liệu. Collection được cung cấp không hỗ trợ vai trò tích lũy cần thiết. Nếu kết quả cuối cần chỉ đọc, dùng collection cho phép tích lũy rồi áp dụng một bước hoàn tất phù hợp.

### Bài 5: Chuyển từ collect(toList()) sang Stream.toList()

Mã phía sau đang thêm phần tử vào kết quả. Sau một lần rút gọn cú pháp, thao tác thêm gây `UnsupportedOperationException`.

**Điểm cần giải thích:** hai API có cam kết khác nhau; `Stream.toList` không cho sửa. Nhu cầu sửa nên được nêu rõ bằng loại đích thích hợp, không dựa vào việc phiên bản hiện tại của `Collectors.toList` từng cho sửa.

### Bài 6: Thu thập song song bằng một list bên ngoài

Người viết dùng `parallelStream().forEach(shared::add)` với `shared` là một `ArrayList`, rồi thấy một lần chạy cho đủ số phần tử.

**Điểm cần giải thích:** chưa có cơ chế cô lập và ghép vùng tích lũy của collector; một lần thành công không chứng minh an toàn. Dùng `collect` đúng cách cho phép thư viện quản lý các kết quả riêng, rồi xem xét chính sách truy cập list sau khi phép thu thập kết thúc.

Khi đọc một lời gọi thu thập, hãy xác định được **kiểu kết quả, cách xử lý phần tử trùng, cam kết thứ tự, quyền sửa và nơi mỗi vùng tích lũy được tạo**. Những thông tin ấy giải thích được vì sao ba bộ thu thập gần giống nhau về cú pháp lại phục vụ những nhu cầu khác nhau.
