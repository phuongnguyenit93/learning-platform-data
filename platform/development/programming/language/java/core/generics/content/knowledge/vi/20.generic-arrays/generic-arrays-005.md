# Trường hợp mảng với `List<?>` có thể tạo hợp lệ trong Java Generics

## 1. Câu hỏi trọng tâm

Trong Java, bạn không thể tạo trực tiếp mảng có kiểu thành phần `List<String>`:

```java
// Không biên dịch:
List<String>[] strings = new List<String>[3];
```

Nhưng đoạn sau **hợp lệ**:

```java
List<?>[] groups = new List<?>[3];
```

Vì sao cả hai đều liên quan Generics mà chỉ biểu thức thứ hai được phép? Câu trả lời là **reifiable type** (*kiểu có thể biểu diễn được tại runtime*) và cơ chế kiểm tra kiểu thành phần của mảng trên JVM.

`List<?>` là một kiểu tham số hóa mà **tất cả type arguments đều là wildcard không giới hạn**. Theo quy tắc Java, kiểu này là **reifiable**, tức đủ điều kiện làm kiểu thành phần cho biểu thức cấp phát mảng `new List<?>[n]`. Ngược lại, `List<String>` và `List<? extends Number>` không reifiable: JVM không thể xác minh các type argument cụ thể đó trong một phép kiểm tra thành phần của mảng.

Bài này giải thích chính xác:

- Vì sao `new List<?>[n]` được Java chấp nhận.
- Mảng thực sự nhớ gì tại runtime và `List<?>[]` cho phép đọc/ghi gì.
- Sự khác biệt giữa `List<?>[]`, raw `List[]`, `List<String>[]` và `List<List<String>>`.
- Rủi ro của covariance, alias kiểu `Object[]`, cast unchecked và heap pollution.
- Cách chọn cấu trúc dữ liệu và kiểm tra phần tử khi ứng dụng cần kiểu cụ thể.
- Cách biên dịch, chạy và đọc lỗi `generic array creation` trên Java 17.

Mục tiêu không phải tìm mẹo vượt qua compiler, mà là hiểu **vì sao một mảng các list không biết kiểu phần tử hợp lệ**, và giới hạn của sự bảo đảm đó.

## 2. Nhắc lại: kiểu mảng và kiểu generic được kiểm tra khác nhau

Một mảng Java có một **runtime component type**. Ví dụ:

```java
String[] names = new String[2];
```

JVM biết object được tạo là `String[]`, bất kể nó được tham chiếu qua biến `String[]`, `Object[]` hay `Object`. Nếu code cố ghi một `Integer` qua alias:

```java
Object[] alias = names;
alias[0] = 42; // ArrayStoreException khi chạy
```

runtime chặn việc ghi vì `Integer` không tương thích với component type thật `String`.

Nhưng collection generic không có một runtime class riêng cho mỗi type argument:

```java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

Hai object được tạo bằng `new ArrayList<>()` có cùng class runtime `ArrayList`; type arguments `String` và `Integer` được compiler dùng để kiểm tra source, không trở thành một class runtime chuyên biệt cho từng object.

Từ đây xuất hiện câu hỏi: nếu JVM chỉ nhìn thấy runtime `List`, làm sao kiểm tra mỗi phần tử của một mảng được công bố là `List<String>[]`? Nó không thể xác minh từng `String` trong những list ấy bằng array store check. Vì vậy Java cấm cấp phát trực tiếp mảng với component type generic **không reifiable**.

### 2.1. So sánh mảng và collection

| Thuộc tính | `String[]` | `List<String>` |
| --- | --- | --- |
| Kiểu thành phần/đối số tại source | `String` | `String` |
| Runtime có object class riêng thể hiện `String`? | Có: array class mang component `String` | Không có specialization riêng `List<String>` |
| Ghi qua alias rộng có được kiểm tra runtime? | Có, có thể ném `ArrayStoreException` | Không có store check theo type argument; raw alias có thể gây heap pollution |
| Quan hệ kiểu | Mảng tham chiếu là covariant | Generic Java thường invariant |
| Kiểm tra một object bằng kiểu tương ứng | `instanceof String[]` hợp lệ | Từ `Object`, `instanceof List<String>` không dùng để kiểm tra type argument runtime |
| Khi đọc sai kiểu có thể gặp lỗi gì? | Array store check thường chặn dữ liệu sai ngay khi ghi | `ClassCastException` có thể xuất hiện khi đọc dữ liệu đã bị nhiễm kiểu |

Đây là lý do không thể áp dụng một cách máy móc mọi quy tắc của `List<T>` cho `T[]`.

## 3. Reifiable type quyết định sự hợp lệ của `new List<?>[n]`

Trong Java, một số kiểu reifiable tiêu biểu gồm:

1. Primitive như `int`, `boolean`.
2. Class/interface không generic như `String`, `Runnable`.
3. Raw type như `List` và `Map`.
4. Parameterized type mà **mọi argument đều là unbounded wildcard `?`**, như `List<?>`, `Map<?, ?>`.
5. Array có component type reifiable, như `String[]`, `List<?>[]`, `List<?>[][]`.

Vì `List<?>` thuộc nhóm 4, `List<?>[]` thuộc nhóm 5. Do đó:

```java
List<?>[] groups = new List<?>[3]; // Hợp lệ
```

Compiler có thể phát sinh thao tác tạo mảng có runtime component class `java.util.List`. Không cần kiểm tra `String`, `Integer` hay subtype cụ thể nào cho type argument vì `?` **không hứa một type argument cụ thể**.

Trái lại:

```java
// Không hợp lệ:
List<String>[] words = new List<String>[3];

// Không hợp lệ:
List<? extends Number>[] numbers = new List<? extends Number>[3];

// Không hợp lệ trong method/class generic:
T[] values = new T[3];
```

Ba component types `List<String>`, `List<? extends Number>` và `T` không reifiable. Chỉ việc có `?` trong một kiểu **không đủ**: phải là unbounded wildcard theo điều kiện của reifiability.

### 3.1. Bảng phân loại

| Biểu thức tạo mảng | Biên dịch? | Lý do |
| --- | --- | --- |
| `new String[3]` | Có | `String` reifiable |
| `new Object[3]` | Có | `Object` reifiable |
| `new List[3]` | Có, có thể cảnh báo `rawtypes` | Raw `List` reifiable |
| `new List<?>[3]` | Có | `List<?>` reifiable |
| `new Map<?, ?>[3]` | Có | Tất cả type arguments đều là wildcard `?` |
| `new List<?>[2][4]` | Có | Component cuối `List<?>` reifiable |
| `new List<String>[3]` | Không | Argument `String` không phải `?` |
| `new List<Object>[3]` | Không | `List<Object>` cũng không reifiable |
| `new List<? extends Number>[3]` | Không | Wildcard có upper bound |
| `new List<? super Integer>[3]` | Không | Wildcard có lower bound |
| `new Map<String, ?>[3]` | Không | Một argument là `String`, không phải `?` |
| `new T[3]` | Không | Type variable `T` không reifiable |

**Quan trọng:** `List<?>` và `List<Object>` không đồng nghĩa. `List<?>` đại diện một list có kiểu phần tử chưa biết. `List<Object>` đại diện list mà bạn có thể thêm các object vào qua tham chiếu được khai báo đúng kiểu, nhưng Java Generics là invariant nên `List<String>` không phải `List<Object>`.

### 3.2. `List<?>[]` thực sự mang component runtime là gì?

Một thí nghiệm:

```java
List<?>[] groups = new List<?>[2];

System.out.println(groups.getClass().getTypeName());
System.out.println(groups.getClass().getComponentType().getTypeName());
```

Với Java 17, kết quả:

```text
java.util.List[]
java.util.List
```

`List<?>[]` là kiểu source giữ wildcard; array object runtime có component `List`. JVM bảo vệ việc ghi **một đối tượng có phải List không**, chứ không bảo vệ type argument của nội dung list.

Kết quả này không phải lỗi erasure; nó phù hợp chính xác với hợp đồng mà `List<?>[]` công bố: các ô mảng là những list, còn kiểu phần tử trong mỗi list **không được xác định**.

## 4. Cấp phát, gán và đọc mảng `List<?>[]`

Ví dụ:

```java
List<?>[] groups = new List<?>[3];

groups[0] = List.of("Java", "Generics");
groups[1] = List.of(10, 20);
groups[2] = List.of(true, false);
```

Cả ba phép gán hợp lệ:

- `groups[0]` chứa tham chiếu tới `List<String>`.
- `groups[1]` chứa `List<Integer>`.
- `groups[2]` chứa `List<Boolean>`.

Mỗi danh sách đều có thể được nhìn như `List<?>`. Mảng không yêu cầu tất cả list có cùng kiểu phần tử cụ thể.

### 4.1. Đọc phần tử qua wildcard

```java
Object first = groups[0].get(0);
System.out.println(first); // Java
```

Phương thức `get` của `List<?>` trả một giá trị mà compiler có thể xem là `Object`. Bạn **không** thể tự động nhận `String`:

```java
// Không biên dịch vì kết quả có kiểu chưa biết:
// String text = groups[0].get(0);
```

Mặc dù trong ví dụ bạn biết `groups[0]` vừa được gán `List.of("Java", ...)`, hợp đồng của mảng nói rằng ô này **có thể chứa một List thuộc kiểu phần tử khác** vào lúc khác. Thông tin đó không được bảo toàn ở kiểu tĩnh `List<?>`.

Nếu cần nhận `String`, hãy kiểm tra:

```java
Object value = groups[0].get(0);

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Hoặc dùng một adapter kiểm tra tất cả phần tử khi muốn tạo `List<String>` đáng tin.

### 4.2. Vì sao không thể `groups[0].add("new")`?

```java
// Không hợp lệ:
// groups[0].add("new");
```

Vì kiểu của `groups[0]` là `List<?>`: dấu `?` được compiler coi như một kiểu phần tử chưa biết. Có thể list thực là `List<Integer>`, nên compiler không cho thêm `String` tùy ý.

Một lời gọi `groups[0].add(null)` có thể được hệ thống kiểu chấp nhận vì `null` tương thích các kiểu tham chiếu, nhưng danh sách runtime có thể bất biến hoặc từ chối null. Các list tạo bằng `List.of(...)` là unmodifiable.

**Mảng có thể thay ô chứa một list khác**:

```java
groups[0] = List.of(99);
```

Điều đó hợp lệ, vì `List<Integer>` vẫn là `List<?>`. Nhưng bạn không được tùy tiện thêm `String` **vào list có kiểu phần tử chưa biết** thông qua tham chiếu `List<?>`.

### 4.3. Cấp phát và tạo nội dung ban đầu

Hai dạng đều hợp lệ:

```java
List<?>[] emptySlots = new List<?>[2];
```

Và:

```java
List<?>[] prepared = new List<?>[] {
    List.of("a", "b"),
    List.of(1, 2)
};
```

Dạng thứ nhất tạo hai ô mang giá trị `null` ban đầu. Dạng thứ hai tạo mảng chứa hai tham chiếu tới list đã có dữ liệu. Nếu dùng `List.of`, chính các list đó không cho phép sửa qua các phương thức cập nhật.

Bạn có thể dùng mảng rỗng:

```java
List<?>[] none = new List<?>[0];
```

Đây là mảng hợp lệ có độ dài 0, hữu ích khi API phải trả array mà chưa có kết quả.

## 5. `List<?>[]` khác raw `List[]` dù có cùng runtime class

Java cũng cho:

```java
List[] rawGroups = new List[2];
```

Lý do tạo mảng hợp lệ tương tự: **raw `List` là reifiable**. Tuy nhiên raw type bỏ nhiều kiểm tra generic tại source và có thể tạo cảnh báo `rawtypes` hoặc `unchecked`.

Ngược lại:

```java
List<?>[] safeGroups = new List<?>[2];
```

diễn đạt rằng mỗi ô chứa một `List` với kiểu phần tử chưa được biết; compiler vẫn bảo vệ quyền thêm phần tử khi bạn đọc list qua ô mảng.

Nếu hai mảng được tạo tương ứng:

```java
List<?>[] wildcard = new List<?>[2];
List[] raw = new List[2];

boolean sameRuntimeClass = wildcard.getClass() == raw.getClass();
```

`sameRuntimeClass` là `true` trên Java thông thường vì component runtime của cả hai đều là raw class/interface `List`.

Nhưng **giống class runtime không có nghĩa giống hợp đồng source**. Dùng `List<?>[]` khi không cần gọi member generic qua raw reference; chỉ dùng `List[]` trong ranh giới legacy với lý do rõ ràng.

### 5.1. `List<?>[]` không đồng nghĩa mảng “không có kiểu”

Cả mảng lẫn list bên trong vẫn có quy tắc:

- Ở cấp mảng, phần tử phải tương thích với component runtime `List` (hoặc `null`).
- Ở cấp `List<?>`, bạn có thể đọc phần tử dưới dạng `Object`, không thể ghi phần tử tùy ý qua tham chiếu wildcard.
- Không có cam kết về sự đồng nhất type arguments của các list ở vị trí khác nhau.
- Không có cam kết rằng list trong mảng là mutable, immutable, không null hoặc cùng độ dài.

Điều kiện reifiability cho phép **tạo** mảng; nó không tự cung cấp tất cả invariant nghiệp vụ.

## 6. Mảng có tính covariance và vẫn có store check

Mảng tham chiếu trong Java là covariant. Vì vậy:

```java
List<?>[] groups = new List<?>[2];
Object[] alias = groups;
```

Phép gán từ `List<?>[]` sang `Object[]` hợp lệ. Nhưng object runtime của `groups` vẫn là một mảng có component class `List`.

Nếu làm:

```java
alias[0] = "not a List";
```

JVM ném `ArrayStoreException`: `String` không thuộc component type `List`.

Ngược lại:

```java
alias[0] = List.of(42);
```

runtime cho phép, vì đối tượng là một `List`. Điều này vẫn đúng dù trước đó `groups[0]` từng chứa `List<String>`. Mảng không thể kiểm tra `String` trên nội dung từng list; `List<?>[]` vốn không hứa điều đó.

### 6.1. Có hai loại kiểm tra khác nhau

| Tình huống | Kiểm tra runtime | Kết quả có thể có |
| --- | --- | --- |
| Đưa `String` vào object array thực tế mang component `List` | JVM kiểm tra object là `List` | `ArrayStoreException` |
| Đưa `List<Integer>` vào mảng có component `List` | JVM kiểm tra object là `List` | Ghi được, không kiểm tra argument `Integer` |
| Đọc list chứa `Integer` qua alias khai báo sai `List<String>` | Compiler/JVM có thể cast kết quả đọc thành `String` | `ClassCastException` |
| Đọc list qua `List<?>` | Không tự cast phần tử thành `String` | Nhận `Object` |

Hai lỗi `ArrayStoreException` và `ClassCastException` không phải một. Lỗi thứ nhất liên quan kiểu phần tử **của mảng**, lỗi thứ hai có thể liên quan giả định generic sai **bên trong list**.

## 7. Cast từ `List<?>[]` sang `List<String>[]` không an toàn

Một số đoạn code cố vượt giới hạn tạo mảng generic bằng cast:

```java
@SuppressWarnings("unchecked")
static List<String>[] unsafeClaim(List<?>[] input) {
    return (List<String>[]) input;
}
```

Phép cast generic có thể sinh unchecked warning (được annotation trong ví dụ cố ý ẩn). JVM biết `input` là mảng các `List`, nhưng không thể kiểm tra mọi list có phần tử `String`.

Ví dụ:

```java
List<?>[] mixed = new List<?>[1];
mixed[0] = List.of(42);

List<String>[] claimed = unsafeClaim(mixed);
String text = claimed[0].get(0); // ClassCastException
```

Cast array không đi duyệt phần tử của từng list. Khi `get(0)` được dùng như `String`, phép kiểm tra `String` thất bại do giá trị thật là `Integer`.

Đừng dùng thủ thuật này để “sửa” lỗi `generic array creation`. Nó chỉ dời lỗi từ compile time tới runtime và có thể tạo **heap pollution** — tình trạng một biến kiểu tham số hóa không còn tham chiếu tới dữ liệu phù hợp với hợp đồng kiểu của nó.

### 7.1. Vì sao cast có thể qua mà giá trị vẫn sai?

Sau erasure, runtime component class của `List<?>[]` là `List`, cũng như biểu diễn runtime cần kiểm tra khi cast về `List<String>[]`. Phần `<String>` không có kiểm tra element type đầy đủ.

Trong mã Java đã được generic checking bảo vệ, `List<String>[]` nếu xuất hiện qua API legacy vẫn có nguy cơ được alias dưới dạng `Object[]` hoặc cast unchecked. Vì vậy chỉ có vẻ ngoài là `List<String>[]` không chứng minh từng list trong đó thật sự chứa String.

### 7.2. Nếu code cũ buộc trả `List<String>[]`?

Nếu một thư viện legacy có API yêu cầu mảng này:

1. Xác định vì sao API không thể đổi sang `List<List<String>>` hoặc một type-safe abstraction khác.
2. Xác định ai tạo, giữ và sửa mảng; có raw alias hoặc `Object[]` alias bên ngoài không?
3. Kiểm tra mọi list và mọi phần tử là `String` trước khi giao dữ liệu cho caller.
4. Nếu buộc cast unchecked, cô lập cast ở phạm vi rất nhỏ và tài liệu hóa invariant; không ẩn cảnh báo ở cấp class.
5. Ưu tiên bản sao và không đưa alias có quyền ghi không kiểm soát ra ngoài.
6. Kiểm thử cả phần tử không hợp lệ, list null và mutation sau khi trả kết quả.

Ngay cả khi validate tại một thời điểm, nếu nơi khác còn quyền sửa cùng list/mảng, invariant vẫn có thể bị phá về sau. Validation và ownership cần được xem cùng nhau.

## 8. Ví dụ Java 17 hoàn chỉnh và kết quả đã kiểm thử

Tạo file **`WildcardListArrayDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardListArrayDemo {
    static <T> List<T> checkedCopy(List<?> input, Class<T> elementType) {
        List<T> result = new ArrayList<>();
        for (Object item : input) {
            result.add(elementType.cast(item));
        }
        return List.copyOf(result);
    }

    @SuppressWarnings("unchecked")
    static List<String>[] unsafeClaim(List<?>[] input) {
        return (List<String>[]) input;
    }

    public static void main(String[] args) {
        List<?>[] rows = new List<?>[3];
        rows[0] = List.of("Java", "Generics");
        rows[1] = List.of(10, 20);
        rows[2] = List.of(true, false);

        System.out.println("array-type=" + rows.getClass().getTypeName());
        System.out.println("component="
                + rows.getClass().getComponentType().getTypeName());
        System.out.println("is-list-array=" + (rows instanceof List<?>[]));
        System.out.println("first-values=" + rows[0].get(0) + ","
                + rows[1].get(0) + "," + rows[2].get(0));
        System.out.println("checked=" + checkedCopy(rows[0], String.class));

        Object[] alias = rows;
        try {
            alias[1] = "not a List";
        } catch (ArrayStoreException e) {
            System.out.println("store=" + e.getClass().getSimpleName());
        }
        alias[1] = List.of(99);
        System.out.println("replaced=" + rows[1].get(0));

        List<String>[] claimed = unsafeClaim(rows);
        try {
            String value = claimed[1].get(0);
            System.out.println(value);
        } catch (ClassCastException e) {
            System.out.println("unchecked=" + e.getClass().getSimpleName());
        }

        List<?>[][] matrix = new List<?>[1][2];
        matrix[0][0] = List.of("left");
        matrix[0][1] = List.of(100);
        System.out.println("matrix=" + matrix[0][0].get(0) + ","
                + matrix[0][1].get(0));
    }
}
```

Biên dịch và chạy bằng JDK có hỗ trợ Java 17:

```bash
javac --release 17 -Xlint:all WildcardListArrayDemo.java
java WildcardListArrayDemo
```

Source trên biên dịch thành công, không có cảnh báo với lệnh lint đã nêu (unchecked cast cố ý minh họa đã được giới hạn tại `unsafeClaim`). Stdout chính xác:

```text
array-type=java.util.List[]
component=java.util.List
is-list-array=true
first-values=Java,10,true
checked=[Java, Generics]
store=ArrayStoreException
replaced=99
unchecked=ClassCastException
matrix=left,100
```

### 8.1. Đọc những dòng liên quan reifiability

`array-type=java.util.List[]` và `component=java.util.List` chứng minh rằng kiểu mảng được tạo có component runtime `List`, không phải `List<String>` hoặc `List<Integer>`.

`is-list-array=true` chứng minh kiểm tra kiểu mảng theo dạng reifiable `List<?>[]` là hợp lệ.

`first-values=Java,10,true` chứng minh một mảng có thể chứa các list với kiểu phần tử khác nhau; khi đọc qua `List<?>`, kết quả được dùng như `Object`.

### 8.2. Đọc các dòng kiểm tra an toàn

`checked=[Java, Generics]` xuất hiện do `checkedCopy` xác minh từng phần tử là `String` bằng `Class<String>.cast`. Adapter trả một list mới; không cần giả định mọi `List<?>` là `List<String>`.

`store=ArrayStoreException` là kết quả của việc đưa `String` vào mảng runtime có component `List`. Đây là lỗi trực tiếp ở **phần tử mảng**.

`replaced=99` chứng minh đưa `List<Integer>` qua cùng alias `Object[]` là hợp lệ, vì object mới vẫn là một `List`.

`unchecked=ClassCastException` cho thấy cast từ `List<?>[]` sang `List<String>[]` không hề xác minh được phần tử `String`; lỗi nổ khi đọc `Integer` như `String`.

`matrix=left,100` chứng minh mảng nhiều chiều `List<?>[][]` cũng có thể tạo, do component cuối `List<?>` reifiable.

### 8.3. Vì sao `checkedCopy` dùng `List.copyOf`?

Hàm:

```java
static <T> List<T> checkedCopy(List<?> input, Class<T> elementType) {
    List<T> result = new ArrayList<>();
    for (Object item : input) {
        result.add(elementType.cast(item));
    }
    return List.copyOf(result);
}
```

đảm bảo mọi phần tử được đưa vào result đã được runtime class token kiểm tra. `List.copyOf` tạo bản sao unmodifiable và **không chấp nhận null**. Nếu contract cho phép null hoặc cần mutable list, chọn cấu trúc copy khác và quy tắc validation rõ ràng.

`Class<T>` chỉ giúp kiểm tra kiểu runtime cụ thể như `String.class`. Nó không thể tự kiểm tra nested generic type `List<String>` ở một phần tử `List<List<String>>` mà không duyệt các cấp lồng nhau.

## 9. Ví dụ cố ý không biên dịch: giới hạn của array creation

Tạo file **`InvalidWildcardArray.java`**:

```java
import java.util.List;

class InvalidWildcardArray<T> {
    void invalid() {
        List<String>[] strings = new List<String>[2];
        List<? extends Number>[] numbers =
                new List<? extends Number>[2];
        T[] values = new T[2];
    }
}
```

Chạy:

```bash
javac --release 17 InvalidWildcardArray.java
```

`javac` từ chối cả ba biểu thức tạo mảng với thông báo cốt lõi:

```text
error: generic array creation
error: generic array creation
error: generic array creation
```

Lý do:

1. `List<String>` không reifiable vì type argument cụ thể `String`.
2. `List<? extends Number>` không reifiable vì `?` có upper bound, không phải wildcard hoàn toàn không giới hạn.
3. `T` không reifiable dù có thể có bound; erasure của `T` không xác định một component class tương ứng với từng lựa chọn `T` của caller.

Đừng nhầm **khai báo biến mảng** với **cấp phát mảng**. Java có thể cho khai báo:

```java
List<String>[] declaredOnly;
```

nhưng không cho tạo trực tiếp bằng `new List<String>[2]`. Một khai báo kiểu mảng generic chưa có object, chưa cung cấp đảm bảo nào về dữ liệu bên trong.

## 10. Dùng `List<?>[]` trong phương thức nhận và trả dữ liệu

Mảng wildcard không chỉ dùng được ở biến cục bộ:

```java
static List<?>[] createGroups() {
    return new List<?>[] {
        List.of("Java"),
        List.of(2026)
    };
}
```

Đây là method minh họa, đặt trong class có `import java.util.List;`. Mảng được tạo có component runtime `List`, và caller có thể quan sát các phần tử như `List<?>`.

Một method nhận mảng:

```java
static int countAll(List<?>[] groups) {
    int count = 0;
    for (List<?> group : groups) {
        count += group.size();
    }
    return count;
}
```

Hàm này không cần `<T>` vì chỉ dùng số phần tử của từng list, không quan tâm kiểu phần tử và không tạo quan hệ giữa các type arguments.

**Cẩn thận với `null`:** `new List<?>[n]` tạo các slot null ban đầu. Nếu gọi `group.size()` trên slot chưa gán sẽ gặp `NullPointerException`. Một API công khai có thể kiểm tra null hoặc có chính sách xem slot null là nhóm rỗng, tùy hợp đồng.

### 10.1. Varargs với `List<?>`

Một tham số varargs được biểu diễn thông qua mảng:

```java
static int total(List<?>... groups) {
    int count = 0;
    for (List<?> group : groups) {
        count += group.size();
    }
    return count;
}
```

Do kiểu thành phần `List<?>` reifiable, dạng varargs này không gặp chính cảnh báo *non-reifiable varargs parameter* thường thấy với `List<String>...` hoặc `List<T>...`.

Ví dụ gọi:

```java
int total = total(List.of("a", "b"), List.of(1, 2, 3));
// total bằng 5
```

Điều này không có nghĩa varargs array được phép sửa tùy tiện. Một varargs method còn có thể nhận một mảng đã tồn tại, trong khi list bên trong có thể immutable, null hoặc được chia sẻ với caller.

### 10.2. Đối chiếu với generic varargs

```java
static <T> void inspect(List<T>... groups) {
    // ...
}
```

Với `List<T>...`, component `List<T>` không reifiable, nên compiler có thể cảnh báo nguy cơ heap pollution. `@SafeVarargs` chỉ được dùng cho những method được Java cho phép gắn annotation và khi tác giả có cơ sở chứng minh body không thực hiện thao tác không an toàn với varargs array. Annotation **không biến** `List<T>` thành reifiable.

Nếu method không cần liên hệ một `T` cụ thể giữa các list, cân nhắc khai báo `List<?>...` thay vì `List<T>...`. Nếu cần giữ cùng một `T`, phải bảo toàn generic contract và xử lý varargs có chủ đích, không thay đại trà chỉ để xóa warning.

## 11. Khi nào nên dùng `List<List<String>>` thay vì array?

`List<?>[]` thích hợp khi yêu cầu chỉ là một **dãy cố định các list có kiểu phần tử chưa biết** hoặc phải tương tác với API cần array. Nó không phù hợp khi bạn cần đảm bảo tất cả các list con đều chứa `String`.

So sánh:

```java
List<?>[] mixed = new List<?>[2];
mixed[0] = List.of("a");
mixed[1] = List.of(42); // Hợp lệ
```

với:

```java
List<List<String>> groups = new ArrayList<>();
groups.add(List.of("a", "b"));
// groups.add(List.of(42)); // Lỗi compile-time
```

Cấu trúc `List<List<String>>` giữ type argument `String` trong hợp đồng source ở cả hai tầng. Khi code được kiểm tra generic và không có raw/unchecked alias phá hợp đồng, compiler từ chối một list chứa `Integer` tại nơi thêm.

Một số tiêu chí chọn:

| Nhu cầu | Nên cân nhắc | Lý do |
| --- | --- | --- |
| Cần đúng số slot, có thể thay cả list tại mỗi slot | `List<?>[]` | Array có kích thước cố định; slot nhận bất kỳ `List<?>` tương thích. |
| Các list có thể có nhiều kiểu phần tử khác nhau, chỉ đọc | `List<?>[]` hoặc `List<List<?>>` | Không hứa mọi phần tử cùng `T`. |
| Mọi list phải chứa String và cần thay đổi số nhóm | `List<List<String>>` | Giữ hợp đồng generic ở hai tầng; dễ thêm/bớt nhóm. |
| API bắt buộc trả array nhưng cần nhóm String type-safe | Xem xét API khác hoặc adapter có validation và ownership rõ | Không tạo trực tiếp `new List<String>[n]` bằng cú pháp Java hợp lệ. |
| Cần một mảng object thật với component `String` | `String[]` | Array runtime kiểm tra component `String`. |

`List<List<String>>` bản thân cũng **không reifiable**, nhưng có thể dùng để khai báo và tạo object `new ArrayList<>()` do không yêu cầu cấp phát một array có component `List<String>`. Tính an toàn của nó đến từ generic checking ở source, không phải JVM tạo class riêng cho `List<List<String>>`.

## 12. Những hiểu lầm phổ biến

### 12.1. “`new List<?>[n]` hợp lệ vì wildcard tắt kiểm tra kiểu”

Không đúng. `List<?>` vẫn là một kiểu generic được compiler kiểm tra. Chính vì không hứa type argument cụ thể, nó đủ điều kiện **reifiable** để tạo mảng; đồng thời compiler vẫn hạn chế thêm phần tử vào một `List<?>`.

### 12.2. “`List<?>[]` tương đương `List<Object>[]`”

Không. `List<Object>` là parameterized type không reifiable, nên không thể cấp phát `new List<Object>[n]`. Ngoài ra `List<String>` không phải subtype của `List<Object>`, nhưng có thể được nhìn như `List<?>`.

### 12.3. “`List<?>[]` chỉ được chứa list rỗng”

Không. Nó có thể chứa `List<String>`, `List<Integer>`, `List<Boolean>` hoặc các list tương ứng khác. `?` không giới hạn loại phần tử hiện có bên trong list; nó hạn chế điều bạn được phép **giả định và ghi** qua tham chiếu wildcard.

### 12.4. “ArrayStoreException sẽ kiểm tra `String` trong `List<String>`”

Không. Mảng runtime có component class `List`; store check xác minh object được gán có phù hợp `List`, chứ không duyệt các phần tử của list để kiểm tra `String`. Nếu cần bảo đảm `String`, viết validator ở mức phần tử.

### 12.5. “Một cast `(List<String>[]) array` làm dữ liệu type-safe”

Không. Cast có thể được compiler cho qua với unchecked warning nhưng không biến type arguments thành runtime component. Lỗi `ClassCastException` có thể xuất hiện muộn hơn ở chỗ đọc dữ liệu.

### 12.6. “Có wildcard `?` là luôn reifiable”

Không. `List<? extends Number>` và `List<? super Integer>` có wildcard **có giới hạn**, không thỏa điều kiện “mọi argument là unbounded wildcard”. `new List<? extends Number>[n]` bị compiler từ chối.

### 12.7. “Erasure biến mọi mảng thành `Object[]`”

Không. Runtime component type của `String[]` vẫn là `String`, của `List<?>[]` là `List`. Erasure áp dụng tới cách biểu diễn generic/type variables, không tự biến mọi array object đã tạo thành `Object[]`.

### 12.8. “Vì `new List<?>[n]` hợp lệ nên luôn là lựa chọn tốt nhất”

Không. Nếu ứng dụng muốn mọi nhóm cùng `List<String>`, một cấu trúc có generic element type rõ như `List<List<String>>` thường giúp compiler phát hiện lỗi sớm hơn. Chọn array khi thực sự cần array semantics hoặc tương thích API.

## 13. Quy trình sửa lỗi `generic array creation`

Nếu nhìn thấy:

```text
error: generic array creation
```

hãy kiểm tra có đang tạo một trong những dạng như:

```java
new List<String>[n]
new List<? extends Number>[n]
new T[n]
```

Sau đó tự hỏi:

1. **Component type có reifiable không?** `List<?>` có; `List<String>` hoặc `T` không.
2. **Có thật cần array không?** Nếu không, dùng `List<List<T>>` hoặc collection phù hợp.
3. **Các list có cần cùng một type argument cụ thể không?** Nếu có, `List<?>[]` không cung cấp invariant đó.
4. **API có thể nhận cấu trúc với wildcard không?** Nếu chỉ đọc các nhóm chưa biết kiểu, `List<?>[]` có thể diễn đạt đúng contract.
5. **Có dữ liệu từ legacy/raw hoặc unchecked cast không?** Nếu có, cần validate những phần tử mang kiểu cụ thể trước khi công bố kết quả type-safe.
6. **Ai sở hữu mảng và các list bên trong?** Nếu trả alias ra ngoài, caller có thể thay đổi slot; các list cũng có thể mutable.
7. **Có đủ test âm không?** Thử một object không phải List qua `Object[]` alias, một list có phần tử không mong đợi, slot null và mutation sau khởi tạo.

Đừng sửa lỗi bằng cách chuyển toàn bộ code sang raw type hay thêm một unchecked cast ngay tại chỗ cấp phát. Cách đó chỉ giấu vấn đề mất generic type information.

## 14. Bài tập thực hành

### Bài 1 — Phân loại cách cấp phát

Cho các dòng:

```java
List<?>[] a = new List<?>[2];
List<String>[] b = new List<String>[2];
List[] c = new List[2];
List<? extends Number>[] d = new List<? extends Number>[2];
```

Dòng nào cấp phát được?

<details>
<summary>Đáp án</summary>

`a` và `c` cấp phát được: `List<?>` và raw `List` reifiable. Dòng `c` có thể sinh warning `rawtypes`. `b` và `d` không hợp lệ vì `List<String>` và `List<? extends Number>` không reifiable.

</details>

### Bài 2 — Đọc phần tử

```java
List<?>[] rows = new List<?>[1];
rows[0] = List.of("Java");
```

Có thể gán trực tiếp `String text = rows[0].get(0);` không?

<details>
<summary>Đáp án</summary>

Không. Kiểu tĩnh của `rows[0]` là `List<?>`; `get(0)` được đọc dưới dạng `Object`. Nếu cần `String`, kiểm tra giá trị bằng `instanceof String` hoặc adapter đã kiểm tra phần tử. Việc vừa gán một `List<String>` không khiến kiểu khai báo của `rows[0]` đổi thành `List<String>`.

</details>

### Bài 3 — Runtime array store

```java
List<?>[] rows = new List<?>[1];
Object[] alias = rows;
alias[0] = "x";
```

Chuyện gì xảy ra?

<details>
<summary>Đáp án</summary>

`ArrayStoreException` tại lệnh ghi. Array object có component runtime `List`, không chấp nhận `String` như một phần tử của mảng.

</details>

### Bài 4 — Một list có `Integer` có thể vào mảng không?

```java
List<?>[] rows = new List<?>[1];
rows[0] = List.of(99);
```

<details>
<summary>Đáp án</summary>

Có, vì `List<Integer>` tương thích `List<?>`. Mảng không hứa các list trong đó phải chứa String. Đọc phần tử qua `rows[0].get(0)` cho một giá trị kiểu tĩnh là `Object`.

</details>

### Bài 5 — Vì sao `new List<?>[3]` có thể cấp phát nhưng `new List<? super Integer>[3]` không?

<details>
<summary>Đáp án</summary>

`List<?>` có unbounded wildcard, thuộc nhóm parameterized type reifiable. `List<? super Integer>` có wildcard với lower bound, không reifiable và bị từ chối khi dùng làm component của array creation.

</details>

### Bài 6 — Dữ liệu cần hai tầng String

Ứng dụng cần một tập các nhóm, mỗi nhóm chỉ có chuỗi, và số nhóm có thể thay đổi. Nên ưu tiên cấu trúc nào?

<details>
<summary>Đáp án</summary>

Thường chọn `List<List<String>>`. Nó giữ hợp đồng kiểu String qua hai tầng và dễ thêm/bớt nhóm. `List<?>[]` không hứa mọi phần tử của mỗi nhóm là String; kiểu mảng có các slot cố định, không tự thay đổi độ dài.

</details>

## 15. Kết luận

**`new List<?>[n]` hợp lệ vì `List<?>` là reifiable.** Mảng được tạo có runtime component class `List`; JVM có thể kiểm tra object được gán vào mỗi slot có thuộc `List` hay không. Dấu `?` không giới hạn không hứa type argument cụ thể nào, nên mảng có thể chứa `List<String>`, `List<Integer>` hoặc list thuộc kiểu phần tử khác.

Điều này **không** làm `List<String>[]` trở nên có thể tạo trực tiếp, không cho phép tự động đọc `String` từ `List<?>`, và không biến cast unchecked thành phép kiểm tra phần tử. Khi cần một mảng các list chưa biết kiểu, `List<?>[]` biểu đạt hợp đồng hợp lý. Khi cần invariant mỗi list đều chứa `T` cụ thể, hãy ưu tiên API giữ kiểu, collection lồng nhau hoặc adapter validate dữ liệu.