# Chuyển từ raw type về kiểu tham số hóa và xử lý cảnh báo `unchecked` trong Java Generics

## 1. Mục tiêu học tập

**Raw type** (*kiểu thô*) là việc dùng tên một kiểu generic mà bỏ các type argument. Ví dụ `List` là raw type của `List<E>`; `Map` là raw type của `Map<K,V>`. Raw type chủ yếu tồn tại để mã Java cũ, viết trước thời kỳ Generics, có thể tiếp tục tương tác với các API mới.

Khi bảo trì ứng dụng, bạn thường gặp:

```java
List names = new ArrayList();
names.add("Lan");

List<String> typed = names; // Cảnh báo unchecked conversion
```

Chương trình có thể biên dịch, nhưng compiler không thể chứng minh rằng mọi phần tử trong `names` đều là `String`. Nhiệm vụ chuyển đổi không chỉ là thêm `<String>` vào vài khai báo: bạn cần xác định **dữ liệu thực**, **kiểu dự định**, **luồng đọc/ghi** và **ranh giới legacy**.

Sau bài này, bạn có thể:

- Phân biệt raw type, `List<?>`, `List<Object>` và `List<String>`.
- Đọc được cảnh báo `[rawtypes]`, `[unchecked]`, đặc biệt là *unchecked conversion*, *unchecked call* và *unchecked cast*.
- Chuyển khai báo, tham số, kiểu trả về và phương thức tiện ích sang generic một cách có hệ thống.
- Nhận diện *heap pollution* và lý do `ClassCastException` có thể xuất hiện muộn hơn vị trí cảnh báo.
- Dùng `Class<T>` và kiểm tra từng phần tử để chuyển dữ liệu legacy vào cấu trúc có kiểu được bảo đảm.
- Khoanh vùng trường hợp bất khả kháng phải dùng `@SuppressWarnings("unchecked")`, với bằng chứng về invariant thay vì ẩn cảnh báo hàng loạt.

Ví dụ chính sử dụng Java 17+, được biên dịch và chạy để đối chiếu cả cảnh báo lẫn kết quả.

## 2. Raw type thực chất bỏ mất điều gì?

Một collection kiểu tham số hóa:

```java
List<String> names = new ArrayList<>();
names.add("Java");

// names.add(17); // Lỗi biên dịch: int/Integer không phù hợp String.
String first = names.get(0);
```

Tham số kiểu `String` là một **hợp đồng tại compile time**: người gọi chỉ được thêm giá trị tương thích và khi đọc có thể nhận `String` mà không tự viết cast.

Dạng raw:

```java
List names = new ArrayList();
names.add("Java");
names.add(17); // Compiler có thể cảnh báo unchecked call.
```

cho phép lời gọi `add` với nhiều kiểu khác nhau, bởi `List<E>` được dùng mà không có `E` cụ thể. Đây **không phải** một danh sách type-safe chứa mọi loại đối tượng. Nó đơn giản làm mất nhiều kiểm tra generic tại điểm sử dụng.

Các phép gán raw và generic có thể được compiler cho phép vì lý do tương thích ngược, song có thể đi cùng cảnh báo:

```java
List raw = new ArrayList();
List<String> strings = raw; // Unchecked conversion.
```

Kết quả gán **không duyệt hoặc chuyển đổi phần tử**. Nếu `raw` chứa `Integer`, lệnh đọc `String` ở nơi khác có thể ném `ClassCastException`.

### 2.1. `List`, `List<?>`, `List<Object>` khác nhau

| Kiểu | Hợp đồng kiểu | Đọc phần tử | Thêm phần tử |
| --- | --- | --- | --- |
| `List` | Raw; không có type argument để compiler kiểm tra đầy đủ | Thường như `Object` | Có thể gọi `add` với object khác nhau, sinh unchecked warning |
| `List<?>` | List có kiểu phần tử **chưa biết** nhưng vẫn là dạng generic hợp lệ | Đọc như `Object` | Không được thêm phần tử khác `null` qua tham chiếu đó |
| `List<Object>` | Danh sách có phần tử kiểu `Object` | Đọc như `Object` | Thêm được nhiều loại đối tượng |
| `List<String>` | Danh sách có phần tử `String` | Đọc như `String` | Thêm `String` hoặc `null`, tùy chính sách dữ liệu |

Một `List<String>` có thể được nhìn như `List<?>`:

```java
List<String> strings = List.of("a", "b");
List<?> unknown = strings;
Object first = unknown.get(0);
```

Nhưng **không** thể tự ý gán cho `List<Object>`:

```java
// List<Object> values = strings; // Lỗi compile: generic bất biến.
```

Dù `String extends Object`, `List<String>` không phải subtype của `List<Object>`. Vì vậy thay mọi `List` raw bằng `List<Object>` có thể khiến API sai ngữ nghĩa hoặc làm code cũ không biên dịch. Khi chỉ cần quan sát một danh sách chưa biết kiểu phần tử, `List<?>` thường phù hợp hơn.

### 2.2. Raw type khác wildcard

`List<?>` giữ lại việc kiểm tra kiểu generic. Compiler ngăn bạn thêm một giá trị không phù hợp với kiểu phần tử bí ẩn.

```java
static int count(List<?> list) {
    return list.size();
}
```

Hàm chỉ đếm nên không cần một tham số kiểu riêng. Nếu một phương thức cần **giữ mối quan hệ kiểu** giữa input và output, nên dùng phương thức generic:

```java
static <T> T first(List<T> list) {
    return list.get(0);
}
```

`List<?>` không thể thay thế mọi phương thức `<T>`: wildcard diễn đạt “kiểu phần tử không quan trọng/không biết”; biến kiểu `T` diễn đạt “những vị trí này phải có cùng kiểu”.

## 3. Ba loại cảnh báo thường gặp

Hãy biên dịch với các tùy chọn của `javac`:

```bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked YourFile.java
```

Thay `YourFile.java` bằng tên tệp nguồn. `-Xlint:rawtypes` yêu cầu cảnh báo khi dùng raw type không phù hợp; `-Xlint:unchecked` mở cảnh báo các thao tác không thể kiểm tra đầy đủ kiểu trong hệ thống generic. Cảnh báo cụ thể, số dòng và định dạng có thể khác theo phiên bản JDK.

### 3.1. `[rawtypes] found raw type`

Ví dụ:

```java
List values = new ArrayList();
```

Compiler nhận thấy hai kiểu generic `List<E>` và `ArrayList<E>` đều được dùng mà thiếu type argument.

Nếu mọi phần tử thực sự là chuỗi:

```java
List<String> values = new ArrayList<>();
```

Nếu kiểu phần tử hiện chưa biết và chỉ đọc:

```java
void inspect(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Việc đổi thành `List<?>` giúp tránh truyền quyền `add(Object)` không kiểm soát ra ngoài. Tuy nhiên, không nên cố đổi đối tượng thực sự cần thay đổi nội dung thành một API chỉ đọc khi nghiệp vụ vẫn yêu cầu ghi.

### 3.2. `[unchecked] unchecked call to add(E)`

Ví dụ:

```java
List raw = new ArrayList();
raw.add(123);
```

Với raw receiver, compiler không có kiểu `E` cụ thể để kiểm tra đối số `add`. Cảnh báo `unchecked call` chỉ ra **lời gọi sử dụng member generic qua raw type**.

Nếu danh sách phải chứa số nguyên:

```java
List<Integer> integers = new ArrayList<>();
integers.add(123);
```

Chỉ thay khai báo từ `List` sang `List<Integer>` khi điều đó đúng với **mọi nơi ghi**, kể cả các hàm nhận alias của cùng danh sách. Một danh sách đã bị nhiều nơi thêm nhiều kiểu không tương thích phải được sửa luồng dữ liệu, chia theo mô hình domain hoặc kiểm tra/chuyển đổi từng phần tử.

### 3.3. `[unchecked] unchecked conversion`

Ví dụ:

```java
List raw = new ArrayList();
List<String> strings = raw;
```

Phép gán được cho phép vì tương thích ngược, nhưng compiler không thể chứng minh từng phần tử là `String`. Nó không tự động kiểm tra phần tử và không “làm sạch” collection.

Cũng nên chú ý kiểu trả về hoặc tham số của phương thức legacy:

```java
static List loadLegacy() {
    return new ArrayList();
}

// ...
List<String> names = loadLegacy(); // Unchecked conversion.
```

Đổi biến nhận thành `List<String>` chỉ đẩy cảnh báo tới ranh giới sử dụng. Nếu không kiểm soát implementation của `loadLegacy`, hãy chuyển dữ liệu sang danh sách mới bằng phép kiểm tra từng phần tử.

### 3.4. `[unchecked] unchecked cast`

Ví dụ:

```java
Object value = new ArrayList<String>();
List<String> names = (List<String>) value;
```

Cast `List<String>` không thể xác minh **type argument** `String` bằng runtime class của đối tượng. Runtime có thể kiểm tra object là `List`, nhưng không thể kiểm tra một generic specialization như `List<String>`.

Đặc biệt nguy hiểm:

```java
List raw = List.of(123);
List<String> wrong = (List<String>) raw;
String text = wrong.get(0); // Có thể ném ClassCastException.
```

Không có bất kỳ câu lệnh nào trên kiểm tra **từng phần tử** trước khi tạo `wrong`. Việc cast hoàn tất mà không ném lỗi không chứng minh danh sách có đúng kiểu phần tử.

## 4. Vì sao cảnh báo unchecked cần được sửa?

### 4.1. Heap pollution

*Heap pollution* xảy ra khi một biến có kiểu tham số hóa giữ tham chiếu tới một đối tượng không phù hợp với kiểu tham số hóa đã khai báo. Raw alias hoặc unchecked operation có thể tạo tình huống này.

Ví dụ gây lỗi có kiểm soát, tệp **`RawWarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RawWarningDemo {
    public static void main(String[] args) {
        List<String> typed = new ArrayList<>();
        List raw = typed;
        raw.add(123);

        try {
            String value = typed.get(0);
            System.out.println(value);
        } catch (ClassCastException e) {
            System.out.println("ClassCastException");
        }
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked RawWarningDemo.java
java RawWarningDemo
```

`javac` phát cảnh báo chính tại `List raw = typed` (raw type) và `raw.add(123)` (unchecked call). Chương trình **vẫn biên dịch được**, và stdout:

```text
ClassCastException
```

Diễn biến:

1. Một `ArrayList<String>` được tạo qua tham chiếu có kiểu.
2. Raw alias `raw` trỏ đến **cùng object**, không tạo bản sao.
3. `raw.add(123)` chèn `Integer` vào danh sách mà code khác đang tin là chỉ chứa `String`.
4. Lời gọi `typed.get(0)` được compiler xem là biểu thức `String`; kiểm tra/cast về `String` xảy ra trên kết quả đọc và thất bại.

Thông báo unchecked ở vị trí ghi là cảnh báo sớm cho lỗi runtime muộn hơn. Bỏ cảnh báo không có nghĩa phần tử sai đã được tự động loại bỏ.

### 4.2. Type erasure không xóa kiểm tra compile time

Trong JVM, `List<String>` và `List<Integer>` thường cùng dùng class runtime như `ArrayList`. Nhưng trước khi chạy, `javac` vẫn phân tích type argument để ngăn chèn `Integer` qua biến `List<String>`.

Raw type tạo vùng “mất bảo vệ” tại compile time; các cast compiler sinh khi đọc có thể lộ lỗi về sau. Đừng suy luận rằng erasure làm Generics vô ích: chính phần kiểm tra compile time bị raw/unchecked operation bỏ qua là điều cần khôi phục khi migration.

## 5. Xử lý warning theo nguồn mất bảo đảm kiểu

Khi nâng dần một method từ raw sang generic, hãy **phân biệt cụ thể warning trước khi quyết định sửa code**:

| Triệu chứng | Nguồn rủi ro | Bước sửa được ưu tiên |
|---|---|---|
| `List raw`, `new ArrayList()` | Bỏ type arguments | Dùng `List<T>`, `List<?>` hoặc một kiểu cụ thể đúng với dữ liệu |
| `raw.add(value)` | Invocation qua receiver raw | Di chuyển đường ghi sang API typed tại nơi sở hữu dữ liệu |
| `List<String> x = raw` | Unchecked conversion | Xác minh dữ liệu đầu vào hoặc chứng minh invariant từ nơi tạo |
| `(List<String>) object` | Unchecked cast | Kiểm tra từng phần tử; không giả sử cast kiểm tra type argument |
| `@SuppressWarnings("unchecked")` | Chỉ ẩn warning | Giữ duy nhất tại helper nhỏ với rationale và tests |

Ví dụ, sửa `List<String> names = legacy.load()` bằng một cast được suppress không khiến danh sách mới chỉ chứa chuỗi. Một adapter `checkedCopy(List<?>, Class<T>)` có thể xác nhận element class rồi tạo snapshot typed; cần xét `null` và mutation của nguồn.

Sau khi cô lập warning, chạy `javac -Xlint:rawtypes,unchecked`, kiểm tra behavior với dữ liệu trộn và quan sát **nơi lỗi được phát hiện**. Mục này tập trung vào **chứng minh unchecked conversion an toàn**; việc di trú nhiều module, thay public contract và bảo toàn binary compatibility cần được lập kế hoạch riêng, không giải quyết bằng annotation.

## 6. Chuyển raw collection qua adapter kiểm tra dữ liệu

Nếu nguồn là raw `List`, thay vì unchecked cast, có thể kiểm tra **từng phần tử** để xây một collection mới. Dùng `Class<T>` làm runtime type token cho kiểu phần tử cụ thể, chẳng hạn `String.class` hoặc `Order.class`.

Hàm:

```java
static <T> List<T> validatedCopy(List<?> input, Class<T> elementType) {
    List<T> result = new ArrayList<>();
    for (Object item : input) {
        result.add(elementType.cast(item));
    }
    return List.copyOf(result);
}
```

Cách này có vài đặc tính:

- `List<?>` có thể nhận tham chiếu tới nhiều `List` khác nhau mà không yêu cầu giả định mọi phần tử có cùng kiểu cụ thể từ bên gọi.
- `Class<T>.cast(item)` kiểm tra **mỗi phần tử** theo runtime class; nếu sai sẽ ném `ClassCastException`.
- Nếu duyệt thành công, `result` được tạo mới và có kiểu `List<T>` được xây qua giá trị đã kiểm tra.
- `List.copyOf(result)` trả một danh sách không thể sửa qua các phương thức cập nhật thông thường và **không chấp nhận phần tử `null`**; nếu nguồn có `null`, phép tạo bản sao này ném `NullPointerException`.
- Đây là **shallow copy**: nếu phần tử là đối tượng mutable, bản thân các phần tử đó không được sao chép sâu.

Với các kiểu generic lồng nhau như `List<List<String>>`, `Class<List<String>>` không được biểu diễn theo cách thông thường bằng một `Class` runtime chính xác cho toàn bộ type argument. Dùng `Class<List>` chỉ kiểm tra phần tử ngoài là `List`, **không kiểm tra các chuỗi trong nested list**. Nếu muốn đảm bảo cấu trúc lồng nhau, phải validate đệ quy hoặc có parser/schema thể hiện đầy đủ cấu trúc.

### 6.1. Vì sao `instanceof List<String>` không dùng được?

Không thể viết:

```java
// Không biên dịch:
if (value instanceof List<String>) {
}
```

Vì type argument `String` không reifiable. Có thể kiểm tra:

```java
if (value instanceof List<?> list) {
    System.out.println(list.size());
}
```

Nhưng kiểm tra đó **chỉ** chứng minh `value` là một `List`, không bảo đảm các phần tử là `String`. Muốn nâng nó thành `List<String>`, vẫn phải kiểm tra từng giá trị.

### 6.2. Khi cần chuẩn hóa thay vì chỉ kiểm tra

Nếu `legacy()` có dữ liệu không nhất quán, bạn có thể muốn **chuyển đổi** theo nghiệp vụ thay vì ném lỗi. Chẳng hạn field là ID có thể được nhận dưới dạng số nguyên hoặc chuỗi, nhưng việc chuyển tất cả sang `String` cần quy định rõ:

- Số nào được phép chuyển sang ID dạng chữ?
- `null` nghĩa là thiếu dữ liệu hay một giá trị hợp lệ?
- Nếu có object không mong đợi, nên bỏ, ghi nhận lỗi, hay dừng toàn bộ?
- Thứ tự và bản ghi trùng lặp có cần bảo toàn không?

Không nên mặc định gọi `.toString()` cho mọi phần tử: kết quả có thể là chuỗi vô nghĩa, che mất lỗi dữ liệu đầu vào.

## 7. Chương trình Java 17 hoàn chỉnh để thực hành migration

Tạo tệp **`MigrationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class MigrationDemo {
    static List legacyNames() {
        List values = new ArrayList();
        values.add("Lan");
        values.add("Minh");
        return values;
    }

    static <T> List<T> validatedCopy(List<?> input, Class<T> elementType) {
        List<T> result = new ArrayList<>();
        for (Object item : input) {
            result.add(elementType.cast(item));
        }
        return List.copyOf(result);
    }

    static <T> void copy(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<String> names = validatedCopy(legacyNames(), String.class);
        System.out.println("names=" + names);

        List<Number> numbers = new ArrayList<>();
        copy(List.of(3, 5), numbers);
        System.out.println("numbers=" + numbers);

        List<?> unknown = List.of("A", 10);
        System.out.println("unknown-size=" + unknown.size());

        try {
            validatedCopy(List.of("OK", 99), String.class);
        } catch (ClassCastException e) {
            System.out.println("invalid=" + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch:

```bash
javac --release 17 -Xlint:rawtypes -Xlint:unchecked MigrationDemo.java
```

`javac` phát cảnh báo từ **duy nhất hàm legacy** `legacyNames()`:

```text
[rawtypes] found raw type: List
[rawtypes] found raw type: List
[rawtypes] found raw type: ArrayList
[unchecked] unchecked call to add(E) as a member of the raw type List
[unchecked] unchecked call to add(E) as a member of the raw type List
```

Đây là các **dòng nhận diện cảnh báo**, rút từ output compiler; phần location, dòng caret và mô tả bound được bỏ khỏi trích dẫn vì phụ thuộc vị trí file. Với source trên và `javac --release 17`, compiler đã báo **5 warnings**. Không có cảnh báo unchecked từ `validatedCopy` hoặc `copy`: cả hai dùng generic đúng theo hợp đồng.

Chạy:

```bash
java MigrationDemo
```

Stdout chính xác:

```text
names=[Lan, Minh]
numbers=[3, 5]
unknown-size=2
invalid=ClassCastException
```

Giải thích:

- `legacyNames()` mô phỏng mã cũ còn raw type; logic mới chưa tin ngay rằng dữ liệu trả về đúng kiểu.
- `validatedCopy(..., String.class)` duyệt nguồn, cast từng phần tử và trả danh sách mới với kiểu khai báo `List<String>`.
- Hàm `copy` dùng hướng dữ liệu: nguồn `List<? extends T>` để **đọc**, đích `List<? super T>` để **ghi**. Với `List<Integer>` nguồn và `List<Number>` đích, việc copy hợp lệ.
- `List<?> unknown` có thể chứa giá trị được suy luận với kiểu phần tử chưa biết; ở đây chỉ đọc `size()`, nên không cần raw type.
- Lần thử với danh sách `"OK", 99` bị adapter từ chối tại phần tử `Integer`, **trước khi** danh sách sai được trao như một `List<String>` cho caller.

### 7.1. Bước chuyển đổi tiếp theo khi sở hữu legacy API

Sau khi biết và kiểm chứng rằng `legacyNames()` chỉ trả chuỗi, nếu bạn **sở hữu** source của nó, có thể thay phần raw bằng:

```java
static List<String> names() {
    List<String> values = new ArrayList<>();
    values.add("Lan");
    values.add("Minh");
    return List.copyOf(values);
}
```

Nếu tất cả writer đã giữ đúng kiểu, code ở caller có thể gọn hơn:

```java
List<String> names = names();
```

Khi ranh giới nguồn dữ liệu thực sự không còn raw và không có đường ghi sai, adapter kiểm tra cùng cấu trúc có thể không cần nữa. Đừng vội xóa adapter nếu dữ liệu vẫn đến từ bên thứ ba, reflection, file nhập, serialization hoặc API trả `Object` chưa được xác thực.

### 7.2. Kiểm chứng cả compile và runtime

Một chương trình **không có warning** vẫn có thể chứa lỗi logic nghiệp vụ; ngược lại, một project cũ còn warning không đồng nghĩa mọi lời gọi đang thất bại. Để migration có bằng chứng rõ ràng, cần cả:

- Compilation với `-Xlint:rawtypes -Xlint:unchecked`.
- Test luồng input hợp lệ, input sai kiểu, dữ liệu rỗng và `null` nếu API cho phép.
- Kiểm tra caller của hàm vừa đổi signature.
- Kiểm tra bất biến kiểu còn được giữ khi có alias hoặc code bên ngoài thay đổi dữ liệu.
- So sánh hành vi trả về: danh sách mutable hay immutable, thứ tự phần tử, khả năng chấp nhận duplicate và `null`.

`List.copyOf` trong chương trình tạo kết quả không sửa được và từ chối `null`. Nếu hợp đồng cũ yêu cầu mutable hoặc cho phép null, hãy chọn bản sao phù hợp thay vì coi đây là thay thế tương đương hoàn toàn.

## 8. Chuyển chữ ký phương thức và class cũ

### 8.1. Đổi một method chỉ đọc

Trước:

```java
static void logAll(List values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Sau:

```java
static void logAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Hàm không sửa danh sách và không đòi biết kiểu phần tử. Dùng `List<?>` làm hợp đồng đầu vào rõ hơn `List<Object>`, vì cả `List<String>` lẫn `List<Integer>` đều có thể truyền vào.

### 8.2. Đổi một method phải bảo toàn kiểu

Trước:

```java
static Object first(List values) {
    return values.get(0);
}
```

Sau:

```java
static <T> T first(List<T> values) {
    return values.get(0);
}
```

Caller được hưởng type inference:

```java
String name = first(List.of("Java"));
Integer number = first(List.of(7));
```

Lúc này liên hệ `T` giữa tham số và kết quả được giữ ngay trong chữ ký. Nếu đầu vào vẫn là raw `List`, caller vẫn có thể phát sinh cảnh báo; chỉ sửa helper chưa đủ để chứng minh mọi giá trị nguồn.

### 8.3. Đổi class chứa state

Trước:

```java
class OldHolder {
    private Object value;

    Object get() {
        return value;
    }

    void set(Object value) {
        this.value = value;
    }
}
```

Nếu class cần nhiều loại value nhưng mỗi instance chỉ giữ một kiểu xác định:

```java
class Holder<T> {
    private T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

Dùng:

```java
Holder<String> holder = new Holder<>();
holder.set("hello");
String result = holder.get();
```

Mẫu trên không còn phải ép kiểu khi đọc. Tuy nhiên, đừng generify class khi mô hình thực cần một tổng hợp nhiều loại giá trị khác nhau và có quy tắc xử lý riêng. Khi đó có thể dùng một interface domain, một sealed hierarchy hoặc các record rõ nghĩa.

### 8.4. Generic API ở ranh giới thư viện

Giả sử code tiêu thụ một thư viện cũ:

```java
List loadFromLibrary(); // Chữ ký legacy; không tự sửa được.
```

Nếu API ngoài không kiểm tra type argument, hãy thêm adapter ở code mình kiểm soát:

```java
static List<String> readNamesSafely(List<?> incoming) {
    List<String> names = new ArrayList<>();
    for (Object item : incoming) {
        if (!(item instanceof String name)) {
            throw new IllegalArgumentException(
                    "Expected a String name, got: " + item);
        }
        names.add(name);
    }
    return names;
}
```

Khi viết hàm trên thành source độc lập, cần import `java.util.List` và `java.util.ArrayList`. `instanceof String name` là cú pháp pattern matching có sẵn ở Java 17. Trong ví dụ này `null` cũng không thỏa `instanceof String`; hành vi báo lỗi là có chủ đích.

Adapter giúp nơi khác chỉ nhìn thấy `List<String>`, nhưng **không ép thư viện cũ trở nên type-safe**. Nếu thư viện tiếp tục sửa cùng một list, trả về bản sao sau validation giúp tách đối tượng mới khỏi alias nguồn.

## 9. Dùng wildcard cho producer và consumer

Khi chuyển API raw, nhiều trường hợp cần type variable và wildcard thay vì biến tất cả tham số thành `List<T>` giống nhau.

Phương thức chỉ đọc phần tử từ nguồn:

```java
static double total(List<? extends Number> numbers) {
    double sum = 0;
    for (Number number : numbers) {
        sum += number.doubleValue();
    }
    return sum;
}
```

Nhận được `List<Integer>`, `List<Double>` và các subtype phù hợp của `Number`. Nguồn là **producer**, nên `? extends Number` có ý nghĩa.

Phương thức chỉ thêm số nguyên vào đích:

```java
static void seed(List<? super Integer> target) {
    target.add(1);
    target.add(2);
}
```

Có thể gọi với `List<Integer>`, `List<Number>`, `List<Object>`; đích là **consumer**, nên `? super Integer` phù hợp.

Với phương thức copy trong chương trình chạy được:

```java
static <T> void copy(
        List<? extends T> source,
        List<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
```

Quan hệ `T` giữa nguồn và đích không thể diễn đạt đầy đủ bằng hai `List<?>` độc lập nếu cần chuyển phần tử mà không ép kiểu. Quy tắc **PECS** (*Producer Extends, Consumer Super*) là công cụ tốt để thiết kế sau migration, nhưng hãy áp dụng dựa trên quyền đọc/ghi thực sự, không theo thói quen thay mọi raw `List` thành wildcard.

## 10. Khi nào có thể dùng `@SuppressWarnings("unchecked")`?

Một số API legacy, reflection hoặc serialization buộc bạn thực hiện phép cast mà compiler không kiểm tra được type argument đầy đủ. Khi thật sự không có lựa chọn khả thi, có thể giới hạn suppression:

```java
@SuppressWarnings("unchecked")
static <T> List<T> uncheckedBoundary(Object input) {
    return (List<T>) input;
}
```

**Đây chỉ là minh họa cú pháp**, không phải một adapter an toàn. Bản thân method không xác minh `input` là `List<T>` đúng nghĩa; nó thậm chí có thể thất bại nếu input không phải `List`. Không nên copy method này vào production rồi coi cảnh báo đã được giải quyết.

Điều kiện để cân nhắc suppression có trách nhiệm:

1. Chứng minh invariant mà compiler không chứng minh được (ví dụ đối tượng được tạo tại chỗ và **mọi thao tác ghi** qua alias đã được kiểm soát).
2. Đặt suppression ở **phạm vi nhỏ nhất**: một local variable hoặc method nhỏ có vai trò xác định, tránh suppression trên cả class/package.
3. Ghi rõ nguồn bảo đảm kiểu, dữ liệu nào được kiểm tra và điều gì khiến invariant bị phá.
4. Viết test với đầu vào đúng và sai kiểu, đặc biệt nếu có dữ liệu không tin cậy hoặc alias từ bên ngoài.
5. Ưu tiên adapter tạo bản sao với element check khi có thể, vì nó cung cấp bằng chứng runtime rõ ràng.

`@SuppressWarnings("rawtypes")` cũng chỉ ẩn cảnh báo raw type. Việc ẩn `rawtypes` hoặc `unchecked` **không bổ sung kiểm tra kiểu** và không sửa dữ liệu sai.

### 10.1. `Collections.checkedList` hỗ trợ điều gì?

Java có wrapper kiểm tra phần tử khi ghi:

```java
List<String> checked =
        java.util.Collections.checkedList(new ArrayList<>(), String.class);
```

Wrapper kiểm tra các thao tác bổ sung phần tử **đi qua chính wrapper**. Nếu code raw cố thêm giá trị sai qua wrapper, runtime có thể ném `ClassCastException` tại lúc ghi.

Giới hạn quan trọng:

- Wrapper không tự rà soát để sửa mọi phần tử đã tồn tại khi được tạo.
- Nếu có alias trực tiếp đến backing list, code viết qua alias có thể bỏ qua kiểm tra của wrapper.
- Nó không thay thế việc thiết kế public generic signature đúng và loại bỏ raw alias.
- Với type argument lồng nhau, `Class<T>` vẫn không xác minh đầy đủ cấu trúc phần tử generic.

Sử dụng wrapper khi cần một lớp bảo vệ runtime cho các đường ghi legacy; nếu cần **dữ liệu sạch ở đầu ra**, adapter kiểm tra từng phần tử và tạo bản sao thường rõ ràng hơn.

## 11. Những lỗi migration phổ biến

### Lỗi 1 — Thay raw bằng `List<Object>` ở khắp nơi

`List<Object>` không nhận được `List<String>` theo phép gán thông thường. Nếu method chỉ quan sát dữ liệu bất kỳ, dùng `List<?>`. Nếu cần quan hệ kiểu giữa input/output, dùng `<T>`.

### Lỗi 2 — Thêm `@SuppressWarnings` trước khi hiểu cảnh báo

Suppress khiến build bớt thông báo nhưng không thay đổi dữ liệu hoặc quyền ghi. Cảnh báo unchecked thường chỉ ra **ranh giới mất kiểm tra kiểu**; hãy xử lý ranh giới ấy bằng kiểu tham số hóa hoặc validation.

### Lỗi 3 — Cast `List<?>` sang `List<String>` và coi như đã validate

Cast không kiểm tra từng phần tử. Kiểm tra `value instanceof List<?>` cũng chỉ xác minh kiểu collection. Muốn một `List<String>` thật sự sạch từ dữ liệu không tin cậy, duyệt và kiểm tra phần tử.

### Lỗi 4 — Cho rằng raw alias tạo bản sao

```java
List<String> strings = new ArrayList<>();
List raw = strings;
```

Cả hai biến trỏ tới một danh sách. Thao tác ghi qua raw alias có thể làm hỏng hợp đồng của `strings`. Nếu cần tách khỏi dữ liệu legacy, tạo bản sao **sau khi** kiểm tra giá trị.

### Lỗi 5 — Chỉ sửa kiểu biến nhận mà bỏ qua producer

Đổi `List names = legacy()` thành `List<String> names = legacy()` có thể chỉ chuyển vấn đề thành unchecked conversion. Hãy sửa chữ ký producer nếu sở hữu code, hoặc dùng adapter tại boundary nếu không sửa được.

### Lỗi 6 — Quên null, mutability và ordering

Một bản sao được tạo bằng `List.copyOf` là unmodifiable và không chấp nhận null. Nếu dữ liệu cũ có null hoặc caller trông chờ mutable list, migration có thể thay đổi hành vi mặc dù type safety đã được cải thiện. Cần ghi rõ contract đầu ra trước khi chuyển.

### Lỗi 7 — Lẫn `unchecked` với lỗi generic biên dịch cứng

Một số sai lệch kiểu không chỉ là cảnh báo:

```java
List<String> texts = new ArrayList<>();
// texts.add(10); // Compilation error.
```

Compiler từ chối vì biết type argument cụ thể. Trái lại, raw call có thể tiếp tục sau warning. Phân biệt error và warning giúp ưu tiên sửa và tránh “vá” bằng cast không cần thiết.

### Lỗi 8 — Quên các API nhận/đưa dữ liệu qua phương thức generic

Khi đổi chữ ký, cần kiểm tra các method references, lambdas, overloaded methods, overrides và serialization boundaries liên quan. Một chữ ký raw có thể đã vô tình cho phép nhiều giá trị khác nhau; sau migration code sẽ phát lộ những chỗ vi phạm hợp đồng cũ chưa được thiết kế rõ.

## 12. Quy trình kiểm tra cuối cùng khi hoàn tất migration

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Collection chứa đúng kiểu phần tử nào? | Hợp đồng API, producer và mọi writer đã được rà soát. |
| Có raw type nào vẫn cần thiết? | Chỉ còn tại boundary legacy được xác định và giải thích. |
| Có còn unchecked conversion/cast/call không? | `javac -Xlint:rawtypes -Xlint:unchecked` cho kết quả rõ; warning còn lại được khoanh vùng. |
| Nếu dữ liệu từ ngoài vào, ai kiểm tra phần tử? | Adapter kiểm tra runtime hoặc parser/schema chuyên dụng. |
| Có alias có thể ghi sai vào collection không? | Luồng ownership/copy hoặc wrapper được kiểm tra. |
| Null, mutability và thứ tự có còn đúng contract? | Unit/integration tests trên API đã chuyển. |
| Các caller có nhận đúng kiểu trả về? | Biên dịch toàn bộ module và các consumer cần thiết. |
| Suppression có invariant chứng minh được không? | Comment sát đoạn cast, phạm vi nhỏ, kiểm thử sai kiểu. |

Một quy trình thực dụng là sửa **từ producer đến consumer**, đảm bảo mỗi điểm nhận dữ liệu có hợp đồng đã được xác minh, rồi mới xóa cast thủ công trong business logic. Khi API phải duy trì tương thích với caller cũ, tổ chức migration theo từng ranh giới cụ thể giúp giữ an toàn và dễ review.

## 13. Bài tự kiểm tra

**Bài 1.** Đoạn dưới có làm biến `strings` thực sự được kiểm tra mọi phần tử chưa?

```java
List raw = List.of(1, 2);
List<String> strings = raw;
```

<details>
<summary>Đáp án</summary>

Chưa. Có unchecked conversion; không phần tử nào được chuyển thành `String`. Khi đọc một phần tử theo kiểu `String`, có thể phát sinh `ClassCastException`. Nếu nguồn không tin cậy, hãy validate/copy từng phần tử hoặc sửa producer.

</details>

**Bài 2.** Phương thức chỉ nhận một danh sách để in kích thước, nên dùng `List`, `List<Object>` hay `List<?>`?

<details>
<summary>Đáp án</summary>

Dùng `List<?>`: nó nhận danh sách với kiểu phần tử bất kỳ, vẫn dùng generic type checking và không cho chèn giá trị tùy ý thông qua tham chiếu này. `List<Object>` hạn chế caller `List<String>`; raw `List` bỏ mất kiểm tra kiểu.

</details>

**Bài 3.** Vì sao cảnh báo ở `raw.add(123)` có thể gây lỗi khi một method khác đọc `typed.get(0)`?

<details>
<summary>Đáp án</summary>

`raw` và `typed` có thể là hai alias của cùng collection. Raw add bỏ qua kiểm tra generic, tạo dữ liệu không phù hợp với giả định `List<String>`. Khi đọc phần tử và cast về `String`, runtime phát hiện kiểu thực là `Integer`.

</details>

**Bài 4.** Nếu có `List<?>` từ API ngoài, có thể dùng `instanceof List<String>` để kiểm tra không?

<details>
<summary>Đáp án</summary>

Không. `List<String>` không phải kiểu reifiable. Có thể xác minh object là `List<?>`, rồi dùng `Class<String>` hoặc `instanceof String` để kiểm tra từng phần tử khi chuyển sang một danh sách `List<String>` mới.

</details>

**Bài 5.** `@SuppressWarnings("unchecked")` đã làm cho cast an toàn chưa?

<details>
<summary>Đáp án</summary>

Chưa. Annotation chỉ ẩn cảnh báo compiler. Tính an toàn phải dựa trên invariant có bằng chứng hoặc một phép kiểm tra runtime thực sự. Ưu tiên adapter có validation khi dữ liệu có thể sai kiểu.

</details>

## 14. Ghi nhớ

Chuyển raw type sang kiểu tham số hóa là công việc **khôi phục hợp đồng kiểu từ nơi tạo dữ liệu đến nơi sử dụng**. `rawtypes` báo bạn thiếu type argument; `unchecked` báo compiler không chứng minh được một phép gọi, gán hoặc cast là type-safe. Không có warning không thay thế cho kiểm thử, còn việc chỉ ẩn warning không hề sửa hợp đồng dữ liệu.

Với source tự kiểm soát, khai báo rõ `List<T>`, `Map<K,V>` và phương thức `<T>` thích hợp. Với nguồn legacy không đảm bảo dữ liệu, sử dụng `List<?>`, kiểm tra **từng phần tử**, rồi tạo collection mới có kiểu cụ thể. Chỉ khoanh vùng unchecked cast khi invariant được chứng minh và thật sự không thể loại bỏ.