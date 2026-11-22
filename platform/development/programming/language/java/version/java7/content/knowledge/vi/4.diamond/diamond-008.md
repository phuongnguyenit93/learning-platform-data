# Java 7 — Tái cấu trúc khai báo dài bằng diamond mà giữ nguyên hợp đồng kiểu

## Mục tiêu

Khi code Java dùng generic lồng nhau, phần khai báo biến và phần tạo đối tượng có thể lặp lại một danh sách type argument rất dài:

```java
Map<String, List<Integer>> scores =
        new LinkedHashMap<String, List<Integer>>();
```

Từ Java 7, **diamond operator** `<>` cho phép trình biên dịch suy luận các type argument của lớp được tạo trong ngữ cảnh thích hợp:

```java
Map<String, List<Integer>> scores = new LinkedHashMap<>();
```

Hai đoạn trên tạo cùng một loại đối tượng `LinkedHashMap` và giữ **kiểu khai báo của biến** là `Map<String, List<Integer>>`. Đây là cách tái cấu trúc giúp bớt lặp cú pháp **mà không chủ ý đổi hợp đồng kiểu**. Khả năng này vẫn được hỗ trợ trên các JDK hiện nay.

Sau bài học, bạn có thể:

1. Nhận diện phần generic lặp thừa ở biểu thức `new` và rút gọn thành `<>`.
2. Giữ nguyên các ràng buộc compile-time như `Map<String, List<Integer>>`, kiểu phần tử và API mà caller nhìn thấy.
3. Giữ đúng concrete implementation, cách khởi tạo, thứ tự duyệt, tính thay đổi được và các tác dụng phụ của đối tượng.
4. Phân biệt diamond với **raw type** và với `var` của Java hiện đại.
5. Kiểm tra refactor bằng chương trình có đầu ra trước–sau, các ca sai kiểu phải thất bại khi biên dịch và kiểm tra hành vi.

Các chương trình chạy được bằng **JDK 17+**, đồng thời giới thiệu cú pháp diamond bắt đầu từ Java 7 mà vẫn phù hợp hiện nay.

## 1. “Giữ nguyên hợp đồng kiểu” nghĩa là gì?

Hãy tách ba thứ tưởng giống nhau:

- **Kiểu được khai báo ở vị trí sử dụng:** `Map<String, List<Integer>>` nói rằng key là `String` và value là `List<Integer>`. Đây là thông tin compiler dùng để phát hiện việc đưa nhầm kiểu vào map.
- **Lớp cụ thể được khởi tạo:** `new LinkedHashMap<...>()` tạo một `LinkedHashMap`. Nó có tính chất về thứ tự lặp khác `HashMap`; đổi tên lớp sẽ có thể đổi hành vi.
- **Nội dung và chính sách vận hành:** Các list bên trong có thể thay đổi được hay không, dữ liệu được nạp như thế nào, đối tượng có được chia sẻ giữa caller hay không, và đồng thời có cần bảo vệ hay không.

Thay `new LinkedHashMap<String, List<Integer>>()` bằng `new LinkedHashMap<>()` **chỉ thay cách biểu diễn type argument tại chỗ tạo đối tượng**. Việc suy luận kiểu dựa trên ngữ cảnh của biểu thức và giới hạn của generic constructor. Việc thay `LinkedHashMap` thành `HashMap`, thay `ArrayList` thành collection không cho sửa, hay thay `List<Integer>` thành `List<Object>` là **những thay đổi khác**, phải được xem xét riêng.

### Vì sao phải giữ dấu `<>`?

```java
Map<String, List<Integer>> a = new LinkedHashMap<>();
Map<String, List<Integer>> b = new LinkedHashMap();
```

Đây là **hai dòng minh họa**, không phải chương trình độc lập. `a` dùng diamond, compiler suy luận type argument. `b` tạo **raw type** `LinkedHashMap`, thường dẫn đến cảnh báo unchecked conversion khi gán vào kiểu có generic. Raw type làm suy giảm khả năng kiểm tra kiểu ở thời điểm biên dịch. **Đừng xóa cả cặp dấu `<>`** trong lúc rút gọn khai báo.

## 2. Quy tắc chuyển đổi an toàn

Mẫu phổ biến:

```java
// Trước: lặp lại type argument ở hai bên.
Map<String, List<Integer>> groups =
        new LinkedHashMap<String, List<Integer>>();

// Sau: giữ nguyên bên trái và lớp tạo đối tượng.
Map<String, List<Integer>> groups = new LinkedHashMap<>();
```

Ví dụ trên là **hai phương án cho cùng một khai báo**, không đặt cùng lúc vào một scope vì trùng tên `groups`.

Quy tắc thực hiện theo thứ tự:

1. **Giữ nguyên kiểu ở bên trái.** Không đổi `Map<String, List<Integer>>`, tên field/parameter, visibility hay type parameter của phương thức.
2. **Giữ nguyên class sau `new`.** `LinkedHashMap` vẫn là `LinkedHashMap`; `ArrayList` vẫn là `ArrayList`.
3. **Giữ nguyên constructor argument.** Nếu ban đầu có tham số dung lượng, comparator hoặc source collection, đừng tự xóa/sửa các tham số đó chỉ vì muốn dùng diamond.
4. **Chỉ thay phần type argument lặp thừa sau tên generic class** bằng `<>`.
5. **Biên dịch ngay.** Nếu compiler không suy luận được kiểu phù hợp hoặc không còn chọn được constructor như trước, không coi phép biến đổi là an toàn.
6. **Test hành vi quan trọng.** Kiểm tra dữ liệu, thứ tự, sửa đổi đối tượng và API được người gọi sử dụng.

Ví dụ với list:

```java
List<Integer> values = new ArrayList<Integer>(); // Trước
// Tương đương:
List<Integer> values = new ArrayList<>();        // Sau
```

Trong cùng phạm vi, chỉ giữ **một trong hai dòng**. List mới vẫn là `ArrayList` và vẫn cho phép thêm `Integer`; việc thêm `String` vẫn là lỗi kiểu. Diamond không thêm collection mới, không tạo wrapper và không phải cú pháp cast.

### Bảng phân loại thay đổi

| Biến đổi | Có phải rút gọn diamond thuần túy? | Lý do |
| --- | --- | --- |
| `new ArrayList<Integer>()` → `new ArrayList<>()` trong `List<Integer>` | Có, nếu compile/test vẫn đúng | Chỉ rút bớt type argument |
| `new LinkedHashMap<String, List<Integer>>()` → `new LinkedHashMap<>()` | Có, nếu bối cảnh suy luận kiểu phù hợp | Giữ nguyên concrete class |
| `new LinkedHashMap<>()` → `new HashMap<>()` | Không | Có thể đổi thứ tự iteration |
| `List<Integer>` → `List<Object>` | Không | Đổi hợp đồng generic và các phép gán hợp lệ |
| `new ArrayList<>()` → `List.of(...)` | Không | Constructor, nội dung ban đầu và mutability có thể khác |
| `new LinkedHashMap<>()` → `new LinkedHashMap()` | Không | Tạo raw type và có thể phát sinh unchecked warnings |
| `Map<String, List<Integer>> x` → `var x` | Không | Thay cách compiler xác định kiểu của biến; phải đánh giá riêng |

Bài này chỉ thực hiện **rút gọn type argument ở biểu thức tạo đối tượng**. Những biến đổi khác không mặc nhiên an toàn vì bề mặt code đều trông ngắn hơn.

## 3. Thí nghiệm A — Refactor trước/sau với generic lồng nhau

**Yêu cầu:** Lưu danh sách điểm số theo nhóm. Map phải giữ thứ tự các nhóm được chèn; các list bên trong vẫn chỉnh sửa được. Phương thức trả về `Map<String, List<Integer>>` và dữ liệu trước/sau phải bằng nhau.

Dùng `LinkedHashMap` để bảo đảm thứ tự iteration theo thứ tự chèn, và `ArrayList` để chứa các điểm số. Ta thực hiện hai hàm: `before()` viết type argument đầy đủ, `after()` dùng diamond. Hai hàm phải khác **cú pháp**, không khác logic khởi tạo dữ liệu.

Lưu thành `DiamondRefactorDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class DiamondRefactorDemo {
    private static Map<String, List<Integer>> before() {
        Map<String, List<Integer>> groups =
                new LinkedHashMap<String, List<Integer>>();
        List<Integer> core = new ArrayList<Integer>();
        core.add(7);
        core.add(9);
        groups.put("core", core);

        List<Integer> api = new ArrayList<Integer>();
        api.add(8);
        groups.put("api", api);
        return groups;
    }

    private static Map<String, List<Integer>> after() {
        Map<String, List<Integer>> groups = new LinkedHashMap<>();
        List<Integer> core = new ArrayList<>();
        core.add(7);
        core.add(9);
        groups.put("core", core);

        List<Integer> api = new ArrayList<>();
        api.add(8);
        groups.put("api", api);
        return groups;
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> oldValue = before();
        Map<String, List<Integer>> newValue = after();

        System.out.println("before=" + oldValue);
        System.out.println("after=" + newValue);
        System.out.println("equal=" + oldValue.equals(newValue));
        System.out.println("sameClass=" + oldValue.getClass().equals(newValue.getClass()));
        System.out.println("firstKey=" + newValue.keySet().iterator().next());

        newValue.get("core").add(10);
        System.out.println("mutable=" + newValue.get("core"));
    }
}
```

Chạy ở thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 DiamondRefactorDemo.java
java DiamondRefactorDemo
```

Output được kiểm chứng:

```text
before={core=[7, 9], api=[8]}
after={core=[7, 9], api=[8]}
equal=true
sameClass=true
firstKey=core
mutable=[7, 9, 10]
```

**Diễn giải bằng chứng:**

- `before` và `after` có cùng nội dung; `Map.equals` so sánh các entry tương ứng. Đây là một bằng chứng về dữ liệu, không phải chứng minh tự động cho mọi thuộc tính.
- `sameClass=true` vì cả hai tạo `LinkedHashMap`. Diamond không đổi implementation được khởi tạo.
- `firstKey=core` thể hiện thứ tự chèn của `LinkedHashMap` khi dữ liệu thêm `core` trước `api`. Nếu vô tình thay bằng `HashMap` thì không còn được bảo đảm hợp đồng thứ tự này.
- `mutable=[7, 9, 10]` cho thấy list được tạo với `ArrayList` vẫn cho phép thêm phần tử. Diamond không tự chuyển một collection mutable thành immutable.
- Trong mỗi hàm, caller vẫn chỉ thấy chữ ký `Map<String, List<Integer>>`; vị trí khởi tạo `new` không làm đổi kiểu trả về của phương thức.

**Giới hạn của test:** Ví dụ dùng hai object độc lập và dữ liệu nhỏ. Với ứng dụng thật, còn cần kiểm tra những caller phụ thuộc vào việc chia sẻ cùng object, chính sách null, thứ tự, thread-safety, performance và tác dụng phụ của constructor. Không suy ra một lần chạy thành công là đủ cho mọi trường hợp.

## 4. Diamond suy luận từ ngữ cảnh kiểu

### 4.1. Ngữ cảnh khai báo biến

```java
Map<String, List<Integer>> groups = new LinkedHashMap<>();
List<Integer> scores = new ArrayList<>();
```

Compiler nhìn thấy kiểu khai báo mong muốn ở bên trái, rồi kiểm tra lời gọi constructor generic có thể tạo đối tượng phù hợp hay không. `<>` không phải kiểu `Object` được gắn cố định; đối số kiểu được suy luận theo ngữ cảnh.

Chú ý cả **kiểu bên trái** và **constructor bên phải** có vai trò riêng. Khai báo `Map<String, List<Integer>>` ràng buộc giá trị truy cập qua biến `groups`; còn việc chọn `LinkedHashMap` xác định runtime implementation.

### 4.2. Ngữ cảnh kiểu trả về và đối số phương thức trên JDK 17+

Trong code Java 17+, diamond cũng rất hữu ích khi một biểu thức `new` xuất hiện ngay trong `return` hoặc như đối số của hàm có chữ ký generic rõ ràng. Ngữ cảnh cung cấp thông tin cho suy luận kiểu.

Lưu thành `DiamondContextsDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class DiamondContextsDemo {
    private static Map<String, List<Integer>> createReport() {
        return new LinkedHashMap<>();
    }

    private static List<Integer> createBucket() {
        return new ArrayList<>();
    }

    private static void addBucket(Map<String, List<Integer>> report) {
        report.put("java", new ArrayList<>());
        report.get("java").add(17);
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> report = createReport();
        addBucket(report);
        System.out.println("report=" + report);

        List<Integer> scores = createBucket();
        scores.add(21);
        System.out.println("scores=" + scores);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DiamondContextsDemo.java
java DiamondContextsDemo
```

Output:

```text
report={java=[17]}
scores=[21]
```

Với `createReport`, kiểu trả về đã ghi rõ `Map<String, List<Integer>>`; `new LinkedHashMap<>()` có thể suy luận type argument phù hợp trong ngữ cảnh đó. Với `addBucket`, tham số `report.put` mong đợi giá trị `List<Integer>`, nên `new ArrayList<>()` tạo list phù hợp để truyền. Thí nghiệm cũng chứng minh các list tạo ra vẫn thay đổi được.

Không nên hiểu rằng compiler luôn suy luận “đúng ý” trong mọi chỗ viết `new Foo<>()`. Khi ngữ cảnh yếu hoặc quá rộng, kiểu suy luận có thể rộng hơn dự kiến; khi có generic bound/overload phức tạp, kết quả cần được kiểm tra bằng biên dịch và API signature. Đừng xóa một type argument tường minh chỉ vì cú pháp `<>` trông hợp lệ bằng mắt.

### 4.3. Generic lồng nhau sâu hơn

```java
Map<String, Map<String, List<Integer>>> index =
        new LinkedHashMap<>();
Map<String, List<Integer>> section = new LinkedHashMap<>();
List<Integer> chapterScores = new ArrayList<>();
chapterScores.add(17);
section.put("chapter", chapterScores);
index.put("java", section);
```

Đoạn này là **minh họa trong một phương thức**, không phải chương trình độc lập. Các ràng buộc `String`, `Map<String, List<Integer>>`, `List<Integer>` vẫn hiện rõ nơi khai báo biến. Việc giảm lặp type argument không xóa kiểm tra kiểu.

Nếu cấu trúc quá sâu khiến người đọc khó hiểu, có thể cân nhắc một lớp dữ liệu có tên miền nghiệp vụ rõ nghĩa. Đó là **một thay đổi thiết kế riêng**, không phải bước bắt buộc của refactor diamond.

## 5. Giữ nguyên implementation và hành vi ngoài type system

Giả sử code ban đầu dựa vào `LinkedHashMap` để hiển thị theo thứ tự chèn:

```java
Map<String, List<Integer>> values =
        new LinkedHashMap<String, List<Integer>>();
```

Refactor diamond tương ứng:

```java
Map<String, List<Integer>> values = new LinkedHashMap<>();
```

Nếu người sửa vô ý đổi thành `new HashMap<>()` thì **kiểu biến vẫn là `Map<String, List<Integer>>`**, compiler có thể chấp nhận, nhưng yêu cầu **thứ tự iteration theo chèn** không còn được bảo đảm. Hợp đồng kiểu là một phần của hợp đồng chương trình; việc giữ nguyên hành vi còn cần chú ý tới semantics của class và constructor.

### Chương trình kiểm chứng: `DiamondContractDemo.java`

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class DiamondContractDemo {
    private static Map<String, List<Integer>> create() {
        Map<String, List<Integer>> values = new LinkedHashMap<>();
        List<Integer> bucket = new ArrayList<>();
        bucket.add(5);
        values.put("stable", bucket);
        return values;
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> values = create();
        System.out.println("implementation=" + values.getClass().getSimpleName());
        System.out.println("first=" + values.keySet().iterator().next());
        System.out.println("value=" + values.get("stable").get(0));

        values.get("stable").set(0, 6);
        System.out.println("afterUpdate=" + values);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DiamondContractDemo.java
java DiamondContractDemo
```

Output:

```text
implementation=LinkedHashMap
first=stable
value=5
afterUpdate={stable=[6]}
```

Bài này cho thấy ba thuộc tính cần kiểm chứng khi rút gọn code có collection: **lớp cụ thể**, **thứ tự truy cập dữ liệu cần thiết** và **khả năng cập nhật**. Để kiểm tra hợp đồng thứ tự với nhiều phần tử, hãy chạy thêm thí nghiệm A có cả `core` và `api`.

### Các thay đổi phải tránh gộp vào cùng một commit refactor máy móc

- Đổi `LinkedHashMap` thành `HashMap` hoặc `TreeMap`: có thể đổi thứ tự và cách so sánh khóa.
- Đổi `ArrayList` thành `List.of(...)`: có thể đổi khả năng sửa list và việc nhận `null`.
- Đổi constructor từ `new ArrayList<>(existing)` thành `new ArrayList<>()`: mất tác dụng sao chép dữ liệu từ `existing`.
- Đổi `new HashMap<>(capacity)` thành `new HashMap<>()`: có thể đổi cấu hình dung lượng khởi tạo.
- Đổi kiểu parameter, return hoặc field chỉ để bỏ generic dài: có thể thay điều mà module khác được phép biên dịch.
- Thêm `Collections.unmodifiableMap` trong cùng lượt: thay khả năng gọi `put` thông qua wrapper.

Những thay đổi đó có thể có lý do thiết kế riêng, nhưng không được xem là hậu quả tất yếu của diamond.

## 6. Kiểm tra hợp đồng compile-time: ca đúng và ca sai

Một refactor khai báo generic cần giữ việc **chấp nhận dữ liệu đúng kiểu và từ chối dữ liệu sai kiểu**. Ví dụ:

```java
Map<String, List<Integer>> typed = new LinkedHashMap<>();
List<Integer> scores = new ArrayList<>();
scores.add(5);
typed.put("group", scores);
```

Đoạn trong một phương thức này hợp lệ. Nếu viết `scores.add("text");`, compiler từ chối vì `scores` là `List<Integer>`.

Để tự thử lỗi, tạo một file `BadCase.java` có đúng **một** tình huống cố ý sai:

```java
import java.util.ArrayList;
import java.util.List;

public final class BadCase {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>();
        values.add("text"); // CỐ Ý SAI: String không phải Integer
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BadCase.java
```

Kết quả mong đợi: biên dịch **FAIL** (exit code khác 0), không tạo chương trình chạy được từ lần biên dịch này. Thông báo cụ thể có thể khác theo JDK; ý nghĩa là `String` không thể truyền vào `List<Integer>.`

Có thể thử từng dòng sai sau trong một lớp kiểm chứng phù hợp, **mỗi lần một dòng**:

| Ca cần biên dịch thất bại | Lý do |
| --- | --- |
| `List<Integer> v = new ArrayList<>(); v.add("text");` | Generic không chấp nhận `String` thay `Integer` |
| `Map<String, List<Integer>> m = new LinkedHashMap<>(); m.put("x", new ArrayList<String>());` | Value `List<String>` không phù hợp `List<Integer>` |
| `Map<String, List<Integer>> m = new LinkedHashMap<String, List<String>>();` | Type argument cụ thể của map không khớp hợp đồng ở bên trái |
| `List<Integer> a = new ArrayList<>(); List<String> b = a;` | `List<Integer>` không tự chuyển thành `List<String>` |

Trong mọi ca, compiler phải báo lỗi khi biên dịch; đây là **bằng chứng âm** rằng hợp đồng kiểu vẫn được bảo vệ. Để so sánh chính xác trước/sau, áp dụng từng phép thử vào hai phiên bản và xác nhận chúng cùng bị từ chối.

### Vì sao diamond không “đổi generic thành Object”?

Ở dòng:

```java
Map<String, List<Integer>> m = new LinkedHashMap<>();
```

Compiler suy luận type argument thích hợp cho lời gọi constructor. Biến `m` vẫn có kiểu khai báo `Map<String, List<Integer>>`, nên các thao tác trên `m` vẫn được kiểm tra theo kiểu đó.

Dấu `<>` cũng không biến generic thành thông tin runtime đầy đủ. Java dùng **type erasure** cho phần lớn generic; không thể dựa vào `getClass()` để đọc `String` và `Integer` như các type argument được giữ ở runtime. Ta kiểm tra hợp đồng bằng compiler, chữ ký API và test hành vi, không bằng việc mong `LinkedHashMap.class` chứa toàn bộ generic.

## 7. Cẩn thận với `var` khi tái cấu trúc code Java mới

Từ Java 10, `var` cho phép suy luận kiểu biến cục bộ. Đây là tính năng **khác** diamond. Khi rút gọn khai báo dài, đừng đồng thời thay:

```java
Map<String, List<Integer>> report = new LinkedHashMap<>();
```

thành:

```java
var report = new LinkedHashMap<>();
```

và mặc nhiên nghĩ rằng compiler vẫn suy luận `Map<String, List<Integer>>`.

Trong ví dụ thứ hai, nếu không có ngữ cảnh ràng buộc type argument khác, `new LinkedHashMap<>()` được suy luận rộng, dẫn đến kiểu biến cụ thể tương đương `LinkedHashMap<Object, Object>`. Điều này không còn thể hiện hợp đồng `String` → `List<Integer>` ở biến cục bộ. `var` cũng khiến kiểu tĩnh của biến là implementation cụ thể thay vì interface `Map` như khai báo ban đầu.

Ví dụ cố ý sai để phát hiện thay đổi kiểu:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class VarContextFailure {
    public static void main(String[] args) {
        var values = new LinkedHashMap<>();
        Map<String, List<Integer>> typed = values;
    }
}
```

Với `javac --release 17 VarContextFailure.java`, chương trình **không biên dịch**, do `LinkedHashMap<Object, Object>` không thể gán cho `Map<String, List<Integer>>`. Điều này cho thấy chỉ nhìn `new LinkedHashMap<>()` giống nhau là chưa đủ: ngữ cảnh khai báo có thể quyết định kiểu suy luận.

Nếu muốn dùng `var` và thật sự cần type argument cụ thể, có thể giữ type argument ở biểu thức khởi tạo:

```java
var report = new LinkedHashMap<String, List<Integer>>();
```

Tuy nhiên, đó là quyết định **riêng** về phong cách và kiểu tĩnh của biến, không phải refactor diamond tối thiểu. Khi mục tiêu là giữ hợp đồng kiểu dễ thấy, giữ khai báo tường minh phía trái thường rõ hơn.

## 8. Kiểm tra lời gọi constructor và ngữ cảnh API

Suy luận kiểu là công việc của compiler. Khi refactor các biểu thức `new` có constructor argument hoặc API generic phức tạp, hãy kiểm tra thêm:

1. **Tham số constructor được giữ nguyên:** `new ArrayList<Integer>(existingList)` có ý nghĩa tạo bản sao; `new ArrayList<>(existingList)` vẫn truyền cùng argument.
2. **Overload/method binding không đổi ý định:** Khi phương thức overload hoặc generic bound phức tạp, không đoán type inference bằng mắt; biên dịch và kiểm tra đúng API call.
3. **Type argument của generic constructor khác với type argument của class:** `<>` dùng để suy luận type argument của generic class; nó không phải phép viết tắt có thể thay thế tùy ý mọi tham số kiểu của phương thức/constructor.
4. **Public signature vẫn như cũ:** Nếu có client gọi `getScores()` và mong `Map<String, List<Integer>>`, phải giữ nguyên parameter/return type. Mục tiêu là rút trùng lặp trong thân hàm.
5. **Compiler warnings:** Khi thay đổi liên quan raw type, kiểm tra cảnh báo bằng `javac -Xlint:unchecked`. Diamond đúng cách thường giúp tránh các unchecked conversion phát sinh do raw constructor.
6. **Hiệu năng:** Diamond không phải một tối ưu thuật toán hay bộ nhớ; nó không khiến map/list chạy nhanh hơn. Nếu hiệu năng là yêu cầu, đo separately, không gắn kỳ vọng đó cho cú pháp.

### Ví dụ thay đúng và giữ nguyên constructor argument

```java
List<Integer> copy = new ArrayList<Integer>(original);
// Sau:
List<Integer> copy = new ArrayList<>(original);
```

Đây là **hai phương án thay thế** trong một scope có sẵn biến `original` kiểu `List<Integer>`; không khai báo cả hai cùng tên `copy`. Hai biểu thức đều truyền `original` vào copy constructor, nên cùng giữ hành vi tạo list mới chứa các phần tử từ nguồn. Đổi sang `new ArrayList<>()` sẽ thay hành vi.

### Đừng đổi hợp đồng nullable/thread-safety vì code ngắn hơn

Nếu người gọi có thể gọi `put(null, ...)` hoặc các method sửa đổi map, việc chuyển sang implementation/wrapper khác có thể làm thay đổi hợp đồng. Tương tự, diamond không khiến `ArrayList` hoặc `LinkedHashMap` tự trở thành thread-safe. Khi code có chia sẻ giữa các thread, phải xem xét chính sách đồng bộ và concurrency riêng, không coi việc rút gọn generic là cách sửa race condition.

## 9. Quy trình refactor ít rủi ro trong codebase

Thực hiện mỗi cụm thay đổi theo trình tự:

1. **Đọc declaration và caller:** ghi nhận type khai báo, concrete class, các constructor argument, kiểu dữ liệu dự kiến và nơi phụ thuộc vào kết quả.
2. **Lập ảnh chụp hành vi cần giữ:** ví dụ danh sách entry, thứ tự iteration, có thể sửa hay không, cách trả exception hoặc null, khả năng gán vào API hiện tại.
3. **Chỉ rút type argument lặp thừa:** thay `new SomeType<A, B>()` thành `new SomeType<>()` ở chỗ compiler đủ ngữ cảnh; giữ mọi thứ khác nguyên trạng.
4. **Biên dịch:** chạy build/test hiện có; khi muốn kiểm chứng riêng, dùng file Java 17+ và `javac --release 17`.
5. **Đối chiếu kiểm tra kiểu:** thêm hoặc xem ca sai kiểu phải FAIL; xem cảnh báo raw/unchecked để chắc chắn không làm yếu hợp đồng.
6. **Đối chiếu hành vi:** dữ liệu trước/sau, thứ tự, loại collection và phép cập nhật vẫn đúng. Thử đầu vào rỗng, dữ liệu lồng nhau và trường hợp nhạy với thứ tự.
7. **Review diff:** phần thay đổi chỉ nên gồm các type argument bị rút gọn; nếu có thay implementation hay API, tách thành thay đổi được giải thích riêng.

### Ma trận kiểm chứng tối thiểu

| Tiêu chí | Trước | Sau | Bằng chứng nên có |
| --- | --- | --- | --- |
| Kiểu công khai | `Map<String, List<Integer>>` | Không đổi | Chữ ký phương thức/field và mã caller biên dịch |
| Type-safety | Chặn `List<String>` trong value | Không đổi | Ca compile âm |
| Implementation | `LinkedHashMap` | `LinkedHashMap` | Kiểm tra constructor và `getClass()` |
| Thứ tự duyệt | Theo chèn | Theo chèn | Hai key `core` và `api` đúng thứ tự |
| Nội dung | `core=[7,9]`, `api=[8]` | Không đổi | `Map.equals`/test output |
| Mutability | Có thể thêm vào `ArrayList` | Không đổi | Test `add(10)` |
| Constructor args | Không đổi | Không đổi | Review diff và test sao chép/cấu hình |
| Runtime chi phí | Không nhằm tối ưu | Không nhằm tối ưu | Không có giả định hiệu năng mới |

## 10. Lỗi thường gặp

- **Xóa cả `<>`:** `new ArrayList()` là raw constructor, khác với `new ArrayList<>()`. Có thể mất bảo đảm compile-time và sinh cảnh báo unchecked.
- **Làm ngắn cả kiểu bên trái:** Khi đổi `Map<String, List<Integer>>` thành `Map` hoặc `Map<String, Object>`, đã làm thay đổi hợp đồng; compiler không tự bảo toàn ý nghĩa ban đầu.
- **Đổi implementation khi refactor:** `LinkedHashMap` sang `HashMap` có thể đổi thứ tự; code vẫn compile nên cần kiểm tra hành vi.
- **Không giữ constructor args:** `new ArrayList<>(existing)` thành `new ArrayList<>()` làm mất nội dung copy.
- **Cho rằng generic được kiểm chứng ở runtime:** Hầu hết thông tin type argument bị erasure; contract cần được xác nhận qua kiểu khai báo, trình biên dịch và test.
- **Dùng `var` với diamond không có target đủ hẹp:** Có thể suy luận kiểu rộng như `LinkedHashMap<Object, Object>`; phải nhìn kết quả type inference, không chỉ độ ngắn của code.
- **Nhầm diamond với wildcard:** `<>` ở `new` yêu cầu compiler suy luận type argument; `<?>` là wildcard trong kiểu generic và mang ý nghĩa khác. Không thay `<>` bằng `<?>` tại constructor.
- **Kỳ vọng performance tăng:** Diamond là cải thiện khả năng đọc/duy trì source, không đổi thuật toán hay implementation.
- **Dùng phép thử chỉ kiểm tra output một case:** Một ví dụ có thể in ra đúng dù đã đổi thứ tự, khả năng mutate hoặc signature. Chọn test phản ánh hợp đồng người dùng thật sự cần.

## 11. Tự luyện tập và tự đánh giá

**Bài 1 — Rút gọn khai báo:** Viết lại đoạn dưới bằng diamond mà không đổi bất kỳ kiểu khai báo, implementation hay đối số constructor:

```java
Map<String, List<Integer>> topics =
        new LinkedHashMap<String, List<Integer>>();
List<Integer> points = new ArrayList<Integer>();
topics.put("java", points);
```

Đáp án phần rút gọn:

```java
Map<String, List<Integer>> topics = new LinkedHashMap<>();
List<Integer> points = new ArrayList<>();
topics.put("java", points);
```

**Bài 2 — Xác định thay đổi không an toàn:** Tại sao thay `new LinkedHashMap<String, List<Integer>>()` bằng `new HashMap<>()` không phải refactor chỉ dùng diamond? Hãy lập một test thứ tự chèn với hai key.

**Bài 3 — Ca âm kiểm tra kiểu:** Thêm `points.add("bad");` vào đáp án bài 1. Giải thích compiler từ chối ở bước nào và vì sao `<>` không làm biến `points` mất ràng buộc `Integer`.

**Bài 4 — Constructor copy:** Giữ nguyên hành vi sao chép khi đổi `new ArrayList<Integer>(source)` thành diamond. Viết một test sửa list mới mà không làm list nguồn bị thay đổi.

**Bài 5 — `var`:** Vì sao `var map = new LinkedHashMap<>();` không tương đương về kiểu tĩnh với `Map<String, List<Integer>> map = new LinkedHashMap<>();`? Cách nào diễn đạt hợp đồng kiểu rõ ràng hơn trong code cần được nhiều người review?

### Checklist chốt trước khi merge

- [ ] Chỉ thay type argument lặp ở constructor bằng `<>`; không đổi concrete class hay constructor argument.
- [ ] Kiểu field, parameter, local và return quan trọng không đổi nếu mục tiêu là refactor giữ hợp đồng.
- [ ] Không đưa raw type hoặc unchecked conversion mới vào code.
- [ ] Build/test qua JDK dự án; ca đúng kiểu vẫn PASS và ca sai kiểu vẫn FAIL.
- [ ] Những thuộc tính ngoài generic như thứ tự duyệt, null, khả năng sửa, aliasing và đồng thời đã được kiểm chứng nơi chúng là yêu cầu.
- [ ] Không đồng thời đổi sang `var`, collection khác hay wrapper mới mà chưa đánh giá ảnh hưởng riêng.
- [ ] Diff nhỏ, dễ kiểm tra, có lý do rõ ràng cho bất kỳ thay đổi nào vượt khỏi việc dùng diamond.

## Tài liệu chính thức

- [Java Language Specification 17 — Class Instance Creation Expressions, `15.9](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): định nghĩa cú pháp `new` với diamond và việc suy luận type argument.
- [Java Language Specification 17 — Type Inference, Chapter 18](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): cơ chế suy luận kiểu của compiler.
- [Java Language Specification 17 — Parameterized Types, `4.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): hợp đồng generic và kiểu tham số hóa.
- [Oracle Java Tutorials — Type Inference and Diamond](https://docs.oracle.com/javase/tutorial/java/generics/genTypeInference.html): khái niệm suy luận type argument và diamond được giới thiệu từ Java 7.

**Ghi nhớ:** Diamond `<>` là cách bỏ lặp type argument **để compiler suy luận trong ngữ cảnh**, không phải công cụ đổi hợp đồng generic hay thay implementation. Refactor tốt là bản code mới ngắn hơn **và** caller, compile-time checks, constructor, thứ tự, dữ liệu và hành vi quan trọng vẫn giữ nguyên.