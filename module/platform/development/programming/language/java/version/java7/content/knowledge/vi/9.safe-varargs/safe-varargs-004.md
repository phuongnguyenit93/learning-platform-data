# Java 7 — Varargs an toàn: Cảnh báo ở nơi khai báo và nơi gọi

## Mục tiêu bài học

Khi một phương thức Java nhận tham số kiểu `T...`, ta thường gọi rất gọn như `method(a, b, c)`. Nhưng nếu `T` là kiểu generic **không reifiable**, chẳng hạn `List<String>`, lời khai báo `List<String>... groups` có thể tạo ra **cảnh báo ở hai vị trí khác nhau**:

1. **Ở nơi khai báo phương thức (declaration site):** compiler cảnh báo tham số varargs với kiểu phần tử generic không reifiable có khả năng gây **heap pollution**.
2. **Ở nơi gọi phương thức (call site):** compiler cảnh báo khi lời gọi cần tạo mảng varargs có kiểu phần tử generic mà runtime không thể kiểm tra đầy đủ.

Hai cảnh báo có liên quan nhưng **không phải một cảnh báo duy nhất**. Hiểu chúng giúp bạn biết lúc nào cần sửa thiết kế API, lúc nào có thể dùng `@SafeVarargs` một cách có trách nhiệm, và tại sao “hết cảnh báo” không phải bằng chứng mã đã an toàn.

Bài học tập trung vào những khả năng **vẫn dùng được trên Java hiện đại**:

- Cơ chế varargs, mảng được tạo tại lời gọi, type erasure và kiểu reifiable.
- Đọc và tái hiện các cảnh báo của `javac -Xlint:unchecked,varargs` ngay ở declaration và invocation.
- Lý do heap pollution có thể dẫn đến `ClassCastException` dù code generic có vẻ đúng kiểu.
- Cách chọn `@SafeVarargs` khi thực sự bảo đảm implementation không thực hiện thao tác không an toàn.
- Khi nào annotation được phép: constructor, `static`, `final`, và phương thức `private` (được bổ sung vào diện hợp lệ từ Java 9).
- Giới hạn của `@SuppressWarnings("unchecked")` và tình huống nên thay varargs bằng collection.
- Ma trận kiểm thử compile warnings, runtime behavior và những ví dụ **phải FAIL khi biên dịch**.

Toàn bộ chương trình đầy đủ trong bài có thể chạy trên **JDK 17+**. Cú pháp generic varargs và `@SafeVarargs` xuất hiện từ Java 7, nhưng các quy tắc còn hiệu lực hiện nay mới là phạm vi sử dụng được khuyến nghị.

## 1. Varargs thực chất là gì?

Một phương thức có tham số cuối cùng là `T...` cho phép truyền nhiều đối số của kiểu `T`:

```java
static int sum(int... numbers) {
    int result = 0;
    for (int n : numbers) {
        result += n;
    }
    return result;
}
```

Đây là **phương thức minh họa** để đặt trong một lớp Java. Trong thân phương thức, `numbers` có kiểu mảng `int[]`. Bên gọi có thể viết `sum(1, 2, 3)`; với kiểu phần tử reifiable như `int`, không có vấn đề generic heap pollution được nói đến ở đây.

Tình huống phức tạp hơn:

```java
static int count(List<String>... groups) {
    int total = 0;
    for (List<String> group : groups) {
        total += group.size();
    }
    return total;
}
```

Đây cũng là **phương thức minh họa**, cần `import java.util.List;`. Tham số `groups` được nhìn trong method như một mảng các `List<String>`, nhưng Java generic dùng **type erasure**. Ở runtime, kiểu mảng không có khả năng kiểm tra đầy đủ đối số kiểu `String` của từng `List`.

Cú pháp `List<String>...` vẫn **hợp lệ**. Compiler thường **cảnh báo**, không cấm hoàn toàn. Để thấy lý do, cần phân biệt kiểu *reifiable* và *non-reifiable*.

### 1.1. Reifiable và non-reifiable

Một kiểu **reifiable** là kiểu mà thông tin cần thiết để kiểm tra kiểu tồn tại ở runtime theo quy tắc của Java. Ví dụ `String`, `String[]`, `int`, raw `List` và `List<?>` (wildcard không giới hạn) thuộc các trường hợp reifiable phù hợp.

Kiểu `List<String>` **không reifiable**: đối số kiểu `String` không được giữ để runtime xác minh toàn bộ nội dung của một instance `List`. Tương tự, `List<Integer>` và tham số kiểu `T` không được “biến thành” một kiểu runtime đầy đủ chỉ nhờ cú pháp generic.

Với một varargs có phần tử không reifiable:

```java
static void use(List<String>... lists) {
    // Compiler cho phép, nhưng có thể cảnh báo.
}
```

Đây là **mảnh khai báo minh họa**. Nó được viết thành mảng `List<String>[]` tại phạm vi source-level của thân phương thức; runtime không thể bảo đảm từng phần tử mảng chứa đúng danh sách chuỗi. Đây là cửa ngõ có thể phát sinh **heap pollution**.

### 1.2. Vì sao mảng và generic có thể mâu thuẫn?

- Mảng Java có **kiểm tra kiểu thành phần ở runtime**, nhưng trong mảng của loại generic bị erasure, kiểu thành phần runtime không thể biết đủ type argument.
- Java array **covariant**: ví dụ `String[]` có thể được nhìn qua `Object[]`, và phép gán sai kiểu sẽ bị kiểm tra khi chạy.
- Generic thường **invariant**: `List<String>` không thể gán trực tiếp thành `List<Object>` chỉ vì `String` extends `Object`.
- Khi varargs tạo mảng cho phần tử kiểu không reifiable, code có thể tạo ra một đường alias qua `Object[]` để đưa một giá trị có generic type khác vào mảng.
- Compiler không thể kiểm tra tuyệt đối toàn bộ các kiểu bên trong collection ở runtime. Sai sót có thể chỉ bộc lộ khi code lấy phần tử ra và cần chuyển về kiểu `String`, gây `ClassCastException`.

**Kết luận tạm:** `List<String>...` bản thân không có nghĩa “lập tức sai”. Nó tạo **điểm có nguy cơ**. Phương thức chỉ đọc danh sách và không làm rò rỉ/thay đổi mảng theo cách không an toàn có thể đúng; phương thức lưu/ghi/đưa mảng cho code khác có thể nguy hiểm.

## 2. Hai nơi cảnh báo: sơ đồ đường đi compiler

Xét một phương thức chưa gắn `@SafeVarargs`:

```java
static int count(List<String>... groups) {
    int total = 0;
    for (List<String> group : groups) {
        total += group.size();
    }
    return total;
}
```

Và một lời gọi với các đối số riêng lẻ:

```java
int n = count(List.of("A", "B"), List.of("C"));
```

Cả hai mảnh mã nằm trong ngữ cảnh lớp có `import java.util.List`. Phần declaration nêu ra một **chữ ký có khả năng tạo heap pollution**. Ở invocation, compiler cần **đóng gói các đối số vào mảng varargs** có kiểu không reifiable. Vì vậy cùng một feature có thể tạo ra **hai warning tại hai địa điểm source khác nhau**.

```text
DECLARATION SITE
    static int count(List<String>... groups)
                         |
                         +-- non-reifiable varargs element type
                         +-- có thể báo "Possible heap pollution ..."
                         |
                         v
CALL SITE
    count(List.of("A", "B"), List.of("C"))
           |
           +-- lời gọi dạng variable arity
           +-- compiler tạo mảng varargs tương ứng
           +-- có thể báo "unchecked generic array creation ..."
                         |
                         v
METHOD BODY
    groups là một array;
    code an toàn hay không còn phụ thuộc cách thao tác với array.
```

**Đừng suy ra:** “method chỉ đọc nên compiler chắc không cảnh báo.” Compiler thường cảnh báo ngay vì **kiểu của varargs là không reifiable**, không chạy một phép chứng minh ngữ nghĩa đầy đủ trên thân method trước khi xác định mọi chỗ nguy hiểm.

**Cũng đừng suy ra:** mọi lời gọi varargs đều có warning. Warnings phụ thuộc kiểu phần tử, việc có dùng `@SafeVarargs` đúng chỗ hay không, dạng lời gọi và cờ compiler. Để kiểm chứng cụ thể, dùng `-Xlint:unchecked,varargs` và quan sát vị trí thực tế của compiler.

### 2.1. Bảng phân biệt ngắn

| Khía cạnh | Declaration site | Call site |
| --- | --- | --- |
| Ví dụ source | `static void f(List<String>... a)` | `f(List.of("A"), List.of("B"))` |
| Nguyên nhân chính | Tham số varargs có kiểu phần tử non-reifiable | Tạo mảng varargs cho kiểu phần tử non-reifiable khi gọi |
| Cảnh báo thường thấy | `Possible heap pollution from parameterized vararg type ...` | `unchecked generic array creation for varargs parameter ...` |
| Ai thường chịu trách nhiệm giải quyết? | **Tác giả API**: chứng minh thân method an toàn hoặc đổi thiết kế | **Tác giả nơi gọi**: kiểm tra API đã an toàn chưa, lựa chọn call/API phù hợp |
| Annotation được thiết kế cho trường hợp an toàn | `@SafeVarargs` đặt tại method/constructor đủ điều kiện | Caller hưởng lợi vì declaration `@SafeVarargs` hợp lệ có thể loại bỏ call-site warning |
| Cách kiểm tra | `javac -Xlint:unchecked,varargs` tại file khai báo | Cùng lệnh đối với file chứa lời gọi |
| Điều không được làm | Xóa warning bằng annotation nếu thân method vẫn gây heap pollution | Coi không có warning là bảo đảm runtime type-safety |

## 3. Thí nghiệm A — Tái hiện chính xác cảnh báo ở hai vị trí

Lưu thành `DeclarationCallWarningsDemo.java`:

```java
import java.util.List;

public final class DeclarationCallWarningsDemo {
    static int count(List<String>... groups) {
        int total = 0;
        for (List<String> group : groups) {
            total += group.size();
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println("total=" + count(List.of("A", "B"), List.of("C")));
    }
}
```

Biên dịch có bật cảnh báo:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 DeclarationCallWarningsDemo.java
java DeclarationCallWarningsDemo
```

Trên JDK dùng để kiểm chứng, lần biên dịch có **hai cảnh báo**, bản chất tương ứng:

```text
DeclarationCallWarningsDemo.java:4:
warning: [unchecked] Possible heap pollution from parameterized vararg type List<String>

DeclarationCallWarningsDemo.java:13:
warning: [unchecked] unchecked generic array creation for varargs parameter of type List<String>[]

2 warnings
```

Phần trên đã **lược bỏ dấu chỉ cột, phần echo source và định dạng riêng của PowerShell** để tập trung vào hai diagnostic quan trọng. Thông báo, cách xuống dòng và số dòng thực tế có thể khác giữa JDK/cách trình bày terminal. Mục tiêu kiểm thử là thấy **một cảnh báo ở declaration, một ở call site** khi dùng cờ `-Xlint:unchecked,varargs`.

**Stdout khi chạy chương trình:**

```text
total=3
```

### 3.1. Phân tích cảnh báo thứ nhất

Dòng:

```java
static int count(List<String>... groups)
```

là nơi khai báo có kiểu phần tử generic không reifiable. Compiler cảnh báo khả năng heap pollution do sử dụng varargs loại này. **Chữ ký mang rủi ro tiềm tàng**, dù phần thân mẫu chỉ đếm số lượng phần tử và không có thao tác ghi vào mảng.

Điều này không có nghĩa JDK xác định chắc chắn một bug đã xảy ra. Đây là một **cảnh báo tĩnh về khả năng phát sinh vấn đề**. Tác giả API cần phân tích xem mảng có bị sửa, alias, escape hoặc được truyền cho mã có thể thay đổi nó hay không.

### 3.2. Phân tích cảnh báo thứ hai

Dòng:

```java
count(List.of("A", "B"), List.of("C"))
```

là nơi gọi với hai `List<String>` riêng biệt. Lời gọi dạng variable arity có thể cần tạo mảng để truyền các list vào tham số varargs. Vì phần tử là `List<String>` không reifiable, compiler báo *unchecked generic array creation*. Đây là cảnh báo cho **người dùng API tại nơi gọi**, không nhất thiết là chỗ nguy hiểm nằm trong chính caller.

Nếu method nằm trong thư viện và caller ở một file khác, cảnh báo tại caller có thể là điều đầu tiên người dùng thư viện nhìn thấy. Vì vậy giải quyết declaration ở phía thư viện đúng cách có thể cải thiện trải nghiệm cho nhiều caller.

### 3.3. Vì sao chương trình vẫn chạy ra 3?

Mã đếm kích thước các list, không gán sai loại list vào mảng hoặc làm rò rỉ mảng. Với những đầu vào trong ví dụ, hành vi hợp lệ và `total=3`. Nhưng **một lần chạy đúng không xóa rủi ro tổng quát của chữ ký**. Hãy xem phản ví dụ heap pollution bên dưới để thấy điều gì có thể sai.

## 4. Heap pollution thực sự: cảnh báo có lý do tồn tại

**Heap pollution** là tình huống một biến mang kiểu tham số hóa trỏ tới đối tượng không đúng với kiểu đó. Với generic varargs, một cách cố tình tạo lỗi là đổi góc nhìn mảng thành `Object[]` rồi đặt một `List<Integer>` vào vị trí compiler đang tin là `List<String>`.

### Chương trình phản ví dụ: `HeapPollutionDemo.java`

```java
import java.util.List;

public final class HeapPollutionDemo {
    static String first(List<String>... groups) {
        Object[] asObjects = groups;
        asObjects[0] = List.of(42);
        return groups[0].get(0);
    }

    public static void main(String[] args) {
        try {
            System.out.println("value=" + first(List.of("A")));
        } catch (ClassCastException e) {
            System.out.println("caught=" + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 HeapPollutionDemo.java
java HeapPollutionDemo
```

Compiler cảnh báo tại **khai báo** và **lời gọi**, tương tự thí nghiệm A; chương trình vẫn biên dịch. Stdout:

```text
caught=ClassCastException
```

### 4.1. Đường đi gây lỗi

1. Caller tạo list chứa `String` và truyền cho `first`.
2. Trong `first`, mảng varargs được gán thêm bí danh `Object[] asObjects`. Điều này được phép do quan hệ kiểu mảng trong Java.
3. `asObjects[0] = List.of(42)` đưa **`List<Integer>`** vào mảng mà source code xem là `List<String>[]`.
4. Ở runtime, mảng có kiểu thành phần bị erasure, ví dụ `List[]`. Phần runtime check của mảng không phân biệt được `List<Integer>` và `List<String>`, nên phép gán này không bị chặn theo type argument.
5. `groups[0].get(0)` trả một `Integer` trong khi compiler dựa vào generic type `List<String>` và chờ `String`. Việc chuyển kiểu ngầm khi sử dụng kết quả dẫn đến `ClassCastException`.
6. `main` bắt ngoại lệ chỉ để cho output ổn định. Trong ứng dụng thật đây là bug type-safety, không phải kiểu lỗi nên bỏ qua.

**Đừng chạy ví dụ này với dữ liệu thực.** Nó cố tình tạo hành vi không an toàn để minh họa một đường đi mà warning muốn giúp bạn nhận biết.

### 4.2. Tại sao không ném ArrayStoreException ngay lập tức?

Nếu bạn có `String[]` thực, cố đưa một `Integer` vào vị trí của nó qua `Object[]` sẽ bị runtime array store check chặn. Nhưng mảng trong phản ví dụ chứa các phần tử runtime kiểu `List`, và cả `List<String>` lẫn `List<Integer>` đều có instance là `List` sau erasure. Runtime không biết đối số kiểu cần là `String`, nên phép lưu `List.of(42)` không bị chặn ở thời điểm gán; lỗi xuất hiện muộn khi đọc ra như `String`.

Điểm học tập: **type erasure không làm biến mất kiểm tra kiểu của mảng**, nhưng làm cho kiểm tra runtime không đủ chi tiết để bảo đảm generic parameter bên trong.

## 5. Varargs an toàn: điều kiện để `@SafeVarargs` là một cam kết có cơ sở

Java hỗ trợ annotation `@SafeVarargs` để tác giả phương thức hoặc constructor varargs đưa ra cam kết rằng implementation **không thực hiện những thao tác có thể gây unsafe operation trên tham số varargs không reifiable**.

Khi annotation hợp lệ, nó giúp giảm các cảnh báo liên quan:

- Cảnh báo khả năng heap pollution tại khai báo.
- Cảnh báo unchecked generic array creation ở lời gọi variable-arity.
- Nhưng nó **không thực thi một phép chứng minh type-safety đầy đủ**. Nếu tác giả gắn nhãn sai, chương trình vẫn có thể lỗi runtime.
- Với `-Xlint:varargs`, `javac` vẫn có thể cảnh báo những thao tác nguy hiểm **bên trong** một method đã gắn `@SafeVarargs`, ví dụ truyền bí danh mảng vào một nơi có thể gây heap pollution.

### 5.1. Điều kiện đánh giá thân method

Trước khi gắn `@SafeVarargs`, hãy kiểm tra:

1. **Không ghi sai kiểu vào mảng varargs.** Không dùng alias `Object[]` để đặt một list có generic type khác vào.
2. **Không để mảng varargs thoát ra ngoài** trong một trạng thái mà code khác có thể sửa nó trái hợp đồng. Ví dụ lưu vào field chia sẻ hoặc trả về nguyên mảng với kiểu/alias có thể dẫn tới ghi không an toàn.
3. **Không truyền mảng cho helper không an toàn** hoặc API có thể giữ và thay đổi nó mà bạn không kiểm soát.
4. **Không làm lẫn kiểu generic bằng unchecked cast/raw types**. Các casts chỉ để tắt lỗi compiler là một dấu hiệu cần audit.
5. **Chỉ xử lý phần tử theo ràng buộc generic** và tránh đổi mảng. Đọc phần tử và sao chép sang collection mới thường dễ chứng minh hơn.
6. **Không mở rộng lời hứa ngoài những gì đã test/audit.** Nếu implementation thay đổi sau này, phải đánh giá lại annotation.

Một method `@SafeVarargs` có thể gọi helper hoặc dùng reflection, nên việc rà soát phải xem **cả đường đi dữ liệu**, không chỉ có hay không có phép gán trực tiếp `groups[0] = ...`.

## 6. Thí nghiệm B — Một phương thức gắn `@SafeVarargs` an toàn

Mục tiêu: nhận nhiều list, sao chép phần tử của từng list sang một `ArrayList` mới, **không thay đổi và không làm lộ mảng varargs**. Phương thức trả một list mới theo đúng kiểu `T`; kết quả có thể chỉnh sửa được vì implementation chọn `ArrayList`.

### Tệp `SafeJoinDemo.java`

```java
import java.util.ArrayList;
import java.util.List;

public final class SafeJoinDemo {
    @SafeVarargs
    public static <T> List<T> join(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> joined = join(List.of("A", "B"), List.of("C"));
        System.out.println("joined=" + joined);
        System.out.println("size=" + joined.size());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 SafeJoinDemo.java
java SafeJoinDemo
```

Khi kiểm chứng mã mẫu với `-Xlint:unchecked,varargs`, compiler **không phát diagnostic**. Stdout:

```text
joined=[A, B, C]
size=3
```

### 6.1. Lý do có cơ sở để đánh dấu an toàn

- `join` là phương thức `static`, thuộc nhóm được phép gắn `@SafeVarargs`.
- `groups` có kiểu mảng varargs với phần tử generic không reifiable, nhưng thân method chỉ **duyệt và đọc** các nhóm có kiểu phù hợp.
- Mỗi `List<? extends T>` được sao chép phần tử qua `addAll` vào list kết quả.
- Không có alias kiểu `Object[]`, không có ghi phần tử khác loại vào `groups`, không trả về hoặc lưu `groups` cho code bên ngoài.
- Caller nhận `List<T>` mới, không nhận được tham chiếu đến **mảng varargs**. Khi một list nguồn thay đổi sau lời gọi, list kết quả là một danh sách riêng (lưu ý: phần tử object bên trong vẫn có thể là cùng tham chiếu; không phải deep copy).
- Warning biến mất là kết quả của annotation hợp lệ trên mã được audit; **lý do an toàn đến từ cách triển khai**, không đến từ riêng annotation.

### 6.2. Sao chép collection không có nghĩa deep copy

Nếu `T` là một object có thể thay đổi, `result.addAll(group)` sao chép **tham chiếu phần tử**, không clone mỗi object. Mục tiêu của annotation ở đây là không gây heap pollution từ generic varargs; nó không hứa immutable, thread-safe hay deep copy.

### 6.3. Không tự đổi chữ ký chỉ để có annotation

Nếu một API không cần varargs hoặc không thể chứng minh an toàn, có thể thiết kế API dựa trên `Collection` hoặc `List`, tránh một số rủi ro của generic arrays. Đừng gắn `@SafeVarargs` lên bất cứ method nào chỉ để toàn bộ build không còn warning.

## 7. Thí nghiệm C — Kiểu reifiable với wildcard không giới hạn

Một cách giải quyết khác không dùng annotation là **thay đổi kiểu chấp nhận** nếu hợp đồng API thực sự cho phép. Ví dụ nếu chỉ cần đếm số phần tử mà không đọc chúng như `String`, `List<?>...` có thể phù hợp.

### Tệp `ReifiableWildcardDemo.java`

```java
import java.util.List;

public final class ReifiableWildcardDemo {
    static int count(List<?>... groups) {
        int total = 0;
        for (List<?> group : groups) {
            total += group.size();
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println("count=" + count(List.of("A", "B"), List.of(42)));
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 ReifiableWildcardDemo.java
java ReifiableWildcardDemo
```

Compiler **không phát cảnh báo varargs generic** trong phép thử này. Stdout:

```text
count=3
```

### 7.1. Vì sao cách này hợp lệ?

`List<?>` (unbounded wildcard) là một trường hợp reifiable theo quy tắc kiểu Java, nên kiểu phần tử varargs `List<?>` tránh vấn đề non-reifiable như `List<String>`. Hàm `count` cũng không cần biết generic argument của các list; nó chỉ gọi `size()`.

Nhưng đây **không phải** phép thay thế tương đương cho mọi API. Nếu hợp đồng gốc đòi `List<String>` để đọc/ghi chuỗi, đổi thành `List<?>` sẽ **nới rộng tập đối số được phép truyền** và giảm thông tin kiểu mà method có thể dùng. Ví dụ trên cho phép một `List<Integer>` đúng theo chủ đích mới. Vì thế:

- **Chỉ dùng `List<?>...` khi thực sự không cần kiểu phần tử cụ thể.**
- Không sửa kiểu sang wildcard chỉ để làm warning biến mất mà âm thầm làm đổi hợp đồng.
- Với API cần đồng nhất kiểu `T` giữa các nhóm và trả `List<T>`, `@SafeVarargs` trên một implementation được audit như `SafeJoinDemo` thường rõ hơn.

## 8. `@SafeVarargs` không phải bùa hộ mệnh

Một vấn đề quan trọng: Java cho phép annotation hợp lệ về **vị trí** nhưng compiler không thể đảm bảo implementation hoàn toàn safe trong mọi đường đi. Ta có thể gắn `@SafeVarargs` lên method `static` rồi viết một thân method cố tình gây heap pollution.

### Tệp cố ý nguy hiểm: `UnsafeAnnotatedDemo.java`

```java
import java.util.List;

public final class UnsafeAnnotatedDemo {
    @SafeVarargs
    static String first(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);
        return groups[0].get(0);
    }

    public static void main(String[] args) {
        try {
            System.out.println("value=" + first(List.of("A")));
        } catch (ClassCastException e) {
            System.out.println("caught=" + e.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 UnsafeAnnotatedDemo.java
java UnsafeAnnotatedDemo
```

Trong kiểm thử, compiler phát **một cảnh báo từ `-Xlint:varargs` trong thân method** tại chỗ dùng mảng:

```text
warning: [varargs] Varargs method could cause heap pollution
from non-reifiable varargs parameter groups
1 warning
```

Cảnh báo ở declaration và lời gọi liên quan `[unchecked]` đã bị annotation loại bỏ, **nhưng runtime vẫn lỗi**. Stdout:

```text
caught=ClassCastException
```

### 8.1. Bài học từ kết quả này

- Annotation thể hiện **lời cam kết của tác giả**, không phải runtime validation cho các generic type argument.
- `javac -Xlint:varargs` có thể phát hiện một số thao tác đáng ngờ ngay cả khi có `@SafeVarargs`, nhưng không bảo đảm phát hiện mọi lỗ hổng type-safety trong helper, reflection hoặc code phức tạp.
- **Không dùng `@SafeVarargs` để hợp thức hóa mã đang có warning nguy hiểm.**
- Nếu thấy warning `[varargs]` ở trong thân method đã annotated, cần audit lại biến varargs, alias, nơi lưu và nơi truyền đi.
- Nếu có heap pollution, hãy **sửa thuật toán hoặc API**, không chỉ đổi chỗ suppression.

Đoạn mã này có chủ ý không an toàn chỉ phục vụ học tập. Không dùng nó như một implementation production.

## 9. Những vị trí được phép gắn `@SafeVarargs`

Annotation này chỉ được phép ở **method/constructor varargs** có hình thức phù hợp với quy tắc Java. Ý tưởng là tránh những lời hứa an toàn có thể bị phá bởi một implementation override ở subtype.

Đối với Java 17+:

| Loại phần tử khai báo | Có được dùng `@SafeVarargs`? | Lưu ý |
| --- | --- | --- |
| Constructor có varargs | Có | Constructor không bị override |
| Phương thức `static` có varargs | Có | Không bị override theo cơ chế instance dispatch |
| Phương thức instance `final` có varargs | Có | Không thể override |
| Phương thức instance `private` có varargs | Có (Java 9+) | Private không bị override theo hợp đồng thông thường |
| Phương thức instance public/protected/package-private, **không final** và có thể override | Không | Compiler từ chối annotation vì lời hứa có thể bị một override phá |
| Phương thức không có varargs | Không | `@SafeVarargs` chỉ dành cho khai báo varargs |
| Một câu lệnh ở call site | Không | Annotation áp dụng tại khai báo, không gắn trực tiếp lên lời gọi |

**Ghi chú phiên bản:** Hỗ trợ `@SafeVarargs` ở **private instance method** được bổ sung từ Java 9. Trên JDK 17+, đây là cách dùng hợp lệ, đang được hỗ trợ; không cần ràng buộc bài học vào công cụ cũ.

### 9.1. Chương trình minh họa Java 9+: `PrivateSafeDemo.java`

```java
import java.util.List;

public final class PrivateSafeDemo {
    @SafeVarargs
    private <T> int count(List<? extends T>... groups) {
        int result = 0;
        for (List<? extends T> group : groups) {
            result += group.size();
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("privateTotal=" + new PrivateSafeDemo()
                .count(List.of(1, 2), List.of(3)));
    }
}
```

Chạy:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 PrivateSafeDemo.java
java PrivateSafeDemo
```

Trong kiểm thử, compiler không phát diagnostic; stdout:

```text
privateTotal=3
```

Method `count` là **private**, có varargs, không alias/lưu/ghi mảng nên lời cam kết có cơ sở. Demo này đặc biệt cho thấy **không cần `final` trên một private instance method** chỉ để dùng `@SafeVarargs` từ Java 9 trở đi.

### 9.2. Ca phải bị compiler từ chối: method instance có thể override

Tệp `InvalidInstanceAnnotation.java`:

```java
public class InvalidInstanceAnnotation {
    @SafeVarargs
    public <T> void print(T... values) {
        System.out.println(values.length);
    }
}
```

Biên dịch:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 InvalidInstanceAnnotation.java
```

**Kỳ vọng: FAIL** vì phương thức `public` là instance method có thể override, không `final` hoặc `private`. Lỗi nằm ở **điều kiện sử dụng annotation**, không khẳng định chính body `print` tự gây heap pollution. Nếu thiết kế API cần override, không nên phá extensibility của lớp bằng `final` chỉ để dẹp warning; cân nhắc chữ ký hoặc xử lý warning một cách hợp lý.

### 9.3. Ca phải bị compiler từ chối: method không varargs

Tệp `InvalidNonVarargsAnnotation.java`:

```java
import java.util.List;

public final class InvalidNonVarargsAnnotation {
    @SafeVarargs
    private static void print(List<String> values) {
        System.out.println(values);
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 InvalidNonVarargsAnnotation.java
```

**Kỳ vọng: FAIL** vì tham số là `List<String> values`, không phải varargs `List<String>... values`. Annotation không phải cách đánh dấu “generic nói chung” là an toàn; nó nhắm vào vấn đề varargs.

## 10. Vì sao không tạo thẳng mảng generic?

Khi hiểu varargs, người học thường muốn viết:

```java
List<String>[] lists = new List<String>[2];
```

Đây là **mảnh code cố ý sai**: Java không cho tạo trực tiếp mảng có kiểu phần tử parameterized non-reifiable như vậy. Cùng lý do cơ bản liên quan **type erasure và runtime array store check**: runtime không có đủ thông tin để bảo đảm kiểu `List<String>` của từng phần tử.

### Tệp compile-negative: `InvalidGenericArray.java`

```java
import java.util.List;

public final class InvalidGenericArray {
    static void run() {
        List<String>[] lists = new List<String>[2]; // CỐ Ý SAI
        System.out.println(lists.length);
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 InvalidGenericArray.java
```

**Kỳ vọng: FAIL** với lỗi tương đương `generic array creation`.

Điều thú vị là cú pháp generic varargs vẫn được phép, với cơ chế kiểm soát bằng warning và khả năng `@SafeVarargs` trong trường hợp được chứng minh an toàn. Điều này không có nghĩa có thể thay một array creation bị cấm bằng unchecked cast rồi xem nó như an toàn. Các thao tác unchecked cần được xem xét ở đúng nguồn nguy cơ.

## 11. `@SuppressWarnings("unchecked")` có thay được `@SafeVarargs` không?

**Không nên coi hai annotation là tương đương.**

- `@SuppressWarnings("unchecked")` là cơ chế suppression chung cho cảnh báo `unchecked` ở một phạm vi source code nhất định. Nó **không phải** lời cam kết chuyên biệt của API varargs và thường không cung cấp cùng hiệu quả giảm cảnh báo ở các **file caller khác**.
- `@SafeVarargs` được thiết kế riêng cho lời khai báo varargs an toàn, giúp loại bỏ cảnh báo thuộc nhóm generic varargs ở declaration và invocation khi các điều kiện ngôn ngữ cho phép.
- `@SuppressWarnings` không thay đổi type erasure, không chữa heap pollution và không bảo đảm code không có `ClassCastException`.
- Nếu một dòng local có unchecked cast là cần thiết và có chứng minh rõ, có thể dùng suppression với **phạm vi hẹp nhất** cùng bình luận giải thích và test. Không gắn vào cả lớp/package để che những warning không liên quan.
- Với một method generic varargs có thể chứng minh an toàn và đủ điều kiện, chọn `@SafeVarargs` đúng nghĩa là thông điệp tốt hơn cho caller.

### 11.1. Đừng trộn ba loại bằng chứng

| Điều bạn quan sát | Nó cho biết gì? | Nó **không** chứng minh gì? |
| --- | --- | --- |
| Không có warning khi `javac` dùng cờ mặc định | Compiler chưa hiển thị cảnh báo trong cấu hình ấy | Code chắc chắn an toàn |
| Không có warning khi bật `-Xlint:unchecked,varargs` | Không có warning thuộc nhóm đó trong đường build này | Mọi nhánh runtime/helper đều type-safe |
| `@SafeVarargs` biên dịch hợp lệ | Vị trí annotation hợp lệ về cú pháp và hình thức | Thân method đã được kiểm chứng ngữ nghĩa toàn diện |
| Test output đúng với một bộ đầu vào | Bộ đầu vào ấy không làm lộ bug | Không tồn tại heap pollution ở đầu vào khác |
| Có warning `[varargs]` trong method annotated | Compiler thấy thao tác đáng ngờ cần audit | Compiler đã xác định hết mọi đường gây lỗi |

**Mục tiêu là code an toàn và hợp đồng rõ**, không đơn thuần giảm số dòng warning trong terminal.

## 12. Chọn API thay thế khi generic varargs không cần thiết

Nếu API không thật sự cần cú pháp nhiều đối số, có thể dùng một collection chứa các nhóm:

```java
static int countGroups(List<? extends List<String>> groups) {
    int total = 0;
    for (List<String> group : groups) {
        total += group.size();
    }
    return total;
}
```

Đây là **phương thức minh họa**, cần `import java.util.List`. Lời gọi có thể là `countGroups(List.of(List.of("A", "B"), List.of("C")))`. Thiết kế này tránh mảng varargs không reifiable trong chữ ký của method. Bù lại, caller phải tạo/đưa một outer collection và API không hỗ trợ cách gọi `count(a, b, c)` như trước.

Có thể chọn một trong các hướng:

1. **Giữ varargs, audit và gắn `@SafeVarargs`** khi cần ergonomic API và implementation có cơ sở an toàn.
2. **Dùng `List<?>...`** khi hoàn toàn không cần ràng buộc kiểu phần tử cụ thể (lưu ý có thay đổi contract).
3. **Dùng collection parameter** khi số nhóm/lifetime/typing cần rõ ràng và varargs không mang lại giá trị đáng kể.
4. **Dùng overload không varargs** cho vài trường hợp thực sự cố định nếu muốn giữ contract rõ.
5. **Sửa dữ liệu hoặc helper nguy hiểm** thay vì cố giữ API hiện tại nếu không thể bảo đảm type-safety.

### 12.1. Không chọn raw type như một lối thoát

```java
// Không khuyến nghị để tránh warning generic varargs.
static void process(List... groups) {
    // Mất thông tin kiểu tham số hóa ở API.
}
```

Mã này là minh họa, không phải giải pháp nên dùng. `List` raw làm suy yếu type checking và có thể dẫn tới cảnh báo unchecked ở nơi khác. Việc giảm một cảnh báo không tương đương với thiết kế an toàn.

### 12.2. Không lạm dụng `Object...`

`Object...` là varargs có phần tử reifiable, nhưng chuyển `List<String>...` thành `Object...` để dập warning có thể làm mất contract: caller có thể truyền loại dữ liệu không phù hợp và code phải kiểm tra/cast thủ công. Chỉ chọn nếu API thực sự được thiết kế để nhận nhiều loại giá trị, không phải như một mẹo suppression.

## 13. Quy trình kiểm tra trong codebase và CI

Khi thấy warning về generic varargs, nên kiểm tra theo thứ tự sau.

### 13.1. Bước 1 — Bật diagnostic rõ ràng

```bash
javac --release 17 -Xlint:unchecked,varargs -encoding UTF-8 DeclarationCallWarningsDemo.java
```

Trong dự án dùng Maven/Gradle, cấu hình compiler task tương ứng để truyền các tùy chọn lint. Không cần thay đổi cấu trúc project chỉ để chạy thử; có thể tạo một file Java độc lập trong môi trường sandbox để kiểm chứng.

Nếu CI có yêu cầu warning-free build, cân nhắc `-Werror` **sau khi đã đánh giá mức độ warning và chiến lược xử lý**, không bật rồi vội gắn suppression bừa bãi. Cảnh báo là tín hiệu cần triage.

### 13.2. Bước 2 — Khoanh đúng vị trí

- Warning ở chữ ký: xem `List<T>...`, `T...` hoặc kiểu parameterized không reifiable tại declaration.
- Warning ở lời gọi: xác định lời gọi nào tạo generic varargs array.
- Warning `[varargs]` bên trong method đã annotated: xem alias, việc chuyển mảng tới helper, lưu field và escape.
- Không đánh đồng warning liên quan generic varargs với warning unchecked cast/rawtypes từ một đoạn code khác.

### 13.3. Bước 3 — Quyết định người sửa

**Tác giả API** nên ưu tiên xử lý từ gốc: sửa body không an toàn, đổi signature nếu cần, audit annotation. **Caller** nên xác minh method thực sự an toàn hoặc chọn API thay thế khi không thể sửa thư viện. Việc đặt `@SuppressWarnings` ở từng caller thường che vấn đề mà không xử lý design-level risk.

### 13.4. Bước 4 — Test positive và negative

- **Positive compile:** `SafeJoinDemo`, `ReifiableWildcardDemo`, `PrivateSafeDemo` compile sạch với lint.
- **Positive runtime:** `SafeJoinDemo` trả list đúng kiểu/nội dung; `DeclarationCallWarningsDemo` cho `total=3` nhưng có hai warning.
- **Negative runtime:** `HeapPollutionDemo` và `UnsafeAnnotatedDemo` cố tình tạo `ClassCastException` để cho thấy vì sao warning và annotation cần được hiểu đúng.
- **Negative compile:** các annotation không hợp lệ và generic array creation bị compiler từ chối.
- **Regression:** nếu người khác sửa implementation đã `@SafeVarargs`, lặp lại audit heap-pollution paths và các test.

### 13.5. Bước 5 — Review PR

Đối với thay đổi gắn thêm `@SafeVarargs`, reviewer nên hỏi:

1. Kiểu phần tử varargs có non-reifiable không? Warning nào đã được giải quyết?
2. Method/constructor có thuộc nhóm được phép annotation không?
3. Method có ghi vào `groups`, dùng alias `Object[]`, lưu field hay trả mảng ra ngoài không?
4. Có helper/reflection/unchecked cast nào có thể thay mảng hoặc phá ràng buộc generic không?
5. Có dữ liệu mutable/concurrent được chia sẻ làm thay đổi giả định an toàn không?
6. Test có phân biệt “không có warning” với “không thể có heap pollution” không?
7. Annotation có được tài liệu hóa bằng lý do an toàn, không chỉ “to suppress warning” không?

Nếu code mới làm thay đổi cách dùng của caller, cần xem xét API compatibility và test các caller quan trọng chứ không chỉ đánh giá một file library.

## 14. Tổng hợp sáu chương trình và cảnh báo mong đợi

Bộ test minh họa đã được biên dịch với `javac --release 17 -Xlint:unchecked,varargs`. Kết quả dự kiến:

| Chương trình | Cảnh báo khi biên dịch | Stdout | Bài học |
| --- | --- | --- | --- |
| `DeclarationCallWarningsDemo` | 2 `[unchecked]`: declaration + call site | `total=3` | Hai vị trí warning khác nhau |
| `SafeJoinDemo` | Không | `joined=[A, B, C]` và `size=3` | Annotation đi kèm implementation an toàn |
| `ReifiableWildcardDemo` | Không | `count=3` | Wildcard không giới hạn là reifiable; contract rộng hơn |
| `HeapPollutionDemo` | 2 `[unchecked]` | `caught=ClassCastException` | Thực tế có thể xảy ra heap pollution |
| `PrivateSafeDemo` | Không | `privateTotal=3` | Private instance method được phép annotation trên Java 9+ |
| `UnsafeAnnotatedDemo` | 1 `[varargs]` bên trong body | `caught=ClassCastException` | Annotation sai không loại bỏ nguy cơ runtime |

Ba file compile-negative:

| Tệp | Kỳ vọng | Nguyên nhân |
| --- | --- | --- |
| `InvalidInstanceAnnotation.java` | FAIL | `@SafeVarargs` trên instance method có thể override |
| `InvalidNonVarargsAnnotation.java` | FAIL | `@SafeVarargs` trên method không varargs |
| `InvalidGenericArray.java` | FAIL | Tạo mảng `new List<String>[2]` không hợp lệ |

**Ghi chú về số lượng warning:** Đếm ở bảng áp dụng cho đúng mã nguồn và tùy chọn lint được trình bày. Cấu hình compiler, JDK, helper hoặc cách in terminal có thể làm khác câu chữ/định dạng diagnostic. Để xác minh, đọc **vị trí dòng source, mã loại `[unchecked]`/`[varargs]` và lý do** thay vì chỉ so nguyên văn một dòng log.

## 15. Những lỗi hiểu sai phổ biến

### 15.1. “Có warning là method chắc chắn làm hỏng dữ liệu”

Không đúng. `DeclarationCallWarningsDemo` có cảnh báo và chạy đúng với đầu vào minh họa. Compiler báo **khả năng** heap pollution do một kết hợp mảng và generic non-reifiable; không chứng minh method hiện tại đã ghi sai dữ liệu. Điều cần làm là audit implementation.

### 15.2. “Warning chỉ xuất hiện ở nơi khai báo”

Không đúng. Với variable-arity call cần tạo generic varargs array, compiler có thể cảnh báo **ở nơi gọi**; người dùng library có thể thấy warning ngay cả khi không sở hữu source của method.

### 15.3. “`@SafeVarargs` là bằng chứng code an toàn”

Không đúng. `UnsafeAnnotatedDemo` có `@SafeVarargs` hợp lệ về vị trí, nhưng vẫn tạo heap pollution và `ClassCastException`. Annotation là cam kết từ tác giả; cần kiểm tra implementation và call chain.

### 15.4. “Private instance method không thể dùng `@SafeVarargs`”

Không đúng trên Java 17+. Từ Java 9, private instance method có varargs được phép dùng annotation. Không nhầm quy tắc đó với các method instance công khai, không final và có thể override.

### 15.5. “Chỉ dùng `@SuppressWarnings("unchecked")` ở caller là xong”

Không đảm bảo. Suppression không thay đổi runtime semantics và không giải quyết nguy cơ gốc tại method. Nó còn che warning khác nếu đặt quá rộng. Với API an toàn đủ điều kiện, `@SafeVarargs` là cơ chế chuyên biệt hơn.

### 15.6. “Đổi `List<String>...` thành `List<?>...` lúc nào cũng tương đương”

Không. `List<?>` cho phép các list chứa kiểu phần tử khác nhau, nên đổi signature có thể thay đổi contract. Chỉ dùng nếu implementation chỉ cần thao tác không phụ thuộc kiểu phần tử, ví dụ `size()`.

### 15.7. “Mọi mảng đều được tạo thành `Object[]`”

Không chính xác. Runtime array vẫn có kiểu thành phần cụ thể sau erasure (ví dụ `List[]`). Mảng không thể xác thực type argument `String` bên trong list. `Object[]` trong ví dụ heap pollution là một **bí danh hợp lệ** của một mảng kiểu tham chiếu, không có nghĩa đối tượng mảng thật bị đổi kiểu.

### 15.8. “Không thể xảy ra heap pollution nếu không dùng cast”

Không đúng. Alias qua array covariance và erasure có thể dẫn đến trạng thái sai kiểu ở ví dụ. Không nên chỉ tìm dòng `(List<String>)` rồi nghĩ đã audit đủ rủi ro.

### 15.9. “Muốn gọi dễ thì dùng raw types”

Không nên. Raw types làm mất khả năng kiểm tra generic ở compile time và có thể đưa unchecked warnings đến nơi khác. Ưu tiên một API có kiểu rõ ràng, an toàn.

### 15.10. “Một warning biến mất là không cần test”

Không. Build/test cần kiểm tra dữ liệu đúng kiểu, không có array escape, không có unchecked helper và không có runtime type error. Sau khi refactor annotated varargs, hãy giữ test regression để không phá lời hứa `@SafeVarargs`.

## 16. Bài tập tự luyện

**Bài 1 — Hai vị trí diagnostic.** Chạy `DeclarationCallWarningsDemo.java` với `-Xlint:unchecked,varargs`. Gạch chân dòng khai báo `List<String>...` và dòng gọi `count(...)`. Vì sao hai dòng phát warning khác nhau?

**Bài 2 — Tìm đường heap pollution.** Trong `HeapPollutionDemo`, tìm ba bước: tạo alias `Object[]`, gán `List<Integer>`, đọc kết quả như `String`. Vì sao runtime không chặn sớm ngay ở phép gán?

**Bài 3 — Sửa implementation.** Thay method `first` cố ý nguy hiểm bằng một method chỉ **đọc** list, không sửa/làm lộ mảng. Xác minh runtime không còn `ClassCastException` và cân nhắc tính đúng đắn trước khi gắn `@SafeVarargs`.

**Bài 4 — Quyết định annotation.** Với một method `static` duyệt `List<T>...` và sao chép vào `ArrayList<T>` mới, hãy giải thích từng điều kiện khiến việc gắn `@SafeVarargs` có cơ sở.

**Bài 5 — Wildcard.** Thay `List<String>...` bằng `List<?>...` ở hàm chỉ đếm kích thước. Thử truyền cả `List<String>` và `List<Integer>`. Hợp đồng API đã thay đổi như thế nào?

**Bài 6 — Method overrideable.** Thử compile `InvalidInstanceAnnotation.java`. Nếu lớp cần cho phép override, hãy đề xuất một signature khác hoặc cách tổ chức implementation không cần gắn annotation sai luật.

**Bài 7 — Private method.** Chạy `PrivateSafeDemo` và giải thích vì sao private instance method được phép dùng annotation từ Java 9, khác với public non-final instance method.

**Bài 8 — Annotation sai.** Chạy `UnsafeAnnotatedDemo` với cả `-Xlint:unchecked` và `-Xlint:varargs`. Warning nào biến mất, warning nào còn được phát hiện, runtime cho kết quả gì?

**Bài 9 — Collection alternative.** Chuyển một API varargs sang `List<? extends List<String>>`. Lập bảng so sánh ergonomics của call site, kiểu phần tử và khả năng giữ generic contract.

**Bài 10 — Test library.** Giả sử một thư viện có `@SafeVarargs` trên helper được hàng trăm caller dùng. Bạn sẽ kiểm tra source, helper, test và warning thế nào trước khi thay đổi implementation?

### Checklist trước khi merge

- [ ] Nhận diện **declaration-site warning** và **call-site warning** một cách riêng rẽ.
- [ ] Đã bật `javac -Xlint:unchecked,varargs` ở ít nhất một bước kiểm chứng.
- [ ] Phân biệt reifiable `List<?>` với non-reifiable `List<String>`.
- [ ] Không dùng raw type hoặc unchecked cast để dập cảnh báo mà không chứng minh an toàn.
- [ ] Nếu dùng `@SafeVarargs`, method/constructor thuộc nhóm được phép.
- [ ] Đã kiểm tra array alias, ghi sai type, escape, helper và reflection.
- [ ] Không đánh dấu `@SafeVarargs` ở implementation thực sự gây heap pollution.
- [ ] Đã hiểu `@SuppressWarnings` không tự giải quyết nguy cơ từ method.
- [ ] Xem xét collection-based API nếu varargs không cần thiết.
- [ ] Positive compile/runtime và negative compile/runtime đều có bằng chứng.
- [ ] Giữ contract generic của caller; không đổi sang `List<?>` nếu yêu cầu kiểu cụ thể.
- [ ] Reviewer có đủ ngữ cảnh để hiểu vì sao annotation có cơ sở, không chỉ để tắt warning.

## Tài liệu tham khảo chính thức (vẫn áp dụng)

- [Java Language Specification 17 — `9.6.4.7 @SafeVarargs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.7): điều kiện sử dụng annotation và trách nhiệm của người khai báo.
- [Java Language Specification 17 — `8.4.1 Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): variable arity parameters và cảnh báo liên quan non-reifiable type.
- [Java Language Specification 17 — `15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): cách lời gọi variable arity được xử lý.
- [Java Language Specification 17 — `4.7 Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): phân biệt reifiable và non-reifiable.
- [Java SE 17 — SafeVarargs Annotation API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): giải thích annotation và các tác động tại khai báo/lời gọi.
- [Java SE 17 — javac Documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): cách dùng `-Xlint` và kiểm tra diagnostic.

**Kết luận:** Generic varargs với kiểu không reifiable có thể khiến `javac` cảnh báo **ở chỗ khai báo** vì nguy cơ heap pollution và **ở chỗ gọi** vì compiler cần tạo mảng varargs. `@SafeVarargs` là công cụ đúng khi **implementation thật sự an toàn và thuộc nhóm được phép**, không phải cách ép compiler im lặng. Muốn loại bỏ nguy cơ, phải hiểu mảng, erasure, đường alias và hợp đồng generic — rồi kiểm tra bằng **lint + kiểm thử runtime + review implementation**.