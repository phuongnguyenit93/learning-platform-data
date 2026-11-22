# Ý nghĩa cam kết của `@SafeVarargs` trong Java: an toàn kiểu với generic varargs

## 1. Khi nào xuất hiện `@SafeVarargs`?

Varargs (tham số biến đổi số lượng đối số) cho phép truyền nhiều giá trị trong một lần gọi phương thức:

```java
static int sum(int... values) {
    int total = 0;
    for (int value : values) {
        total += value;
    }
    return total;
}
```

Đoạn trên là **phương thức minh họa**, cần đặt trong một lớp. Nó nhận `int...`; đây là kiểu phần tử nguyên thủy và không đặt ra vấn đề generic heap pollution như `List<String>...`.

Với Java generics, có thể muốn nhận **nhiều danh sách** rồi ghép chúng:

```java
import java.util.List;

// Đoạn khai báo đặt trong một lớp Java.
static void printAll(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group);
    }
}
```

Cú pháp này hợp lệ về cơ bản, nhưng Java có thể phát cảnh báo **unchecked** vì `List<String>` là kiểu **không reifiable**: kiểu đối số `String` không được giữ đầy đủ trong thông tin kiểu của mảng ở runtime. Một lời gọi `printAll(List.of("A"), List.of("B"))` cũng có thể sinh cảnh báo khi compiler phải tạo mảng generic varargs tại nơi gọi.

`@SafeVarargs` giải quyết **vấn đề cảnh báo tại khai báo và nơi gọi** khi người viết API đã kiểm tra rằng phần triển khai của phương thức/constructor **không thực hiện thao tác không an toàn trên tham số varargs của kiểu không reifiable**.

Ví dụ:

```java
@SafeVarargs
static void printAllSafely(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group);
    }
}
```

**Đây là một lời cam kết của người viết mã, không phải cơ chế runtime kiểm tra từng phần tử.** Compiler chấp nhận annotation để giảm các cảnh báo tương ứng; trách nhiệm chứng minh nội dung phương thức thật sự an toàn nằm ở người viết và người review API.

`@SafeVarargs` xuất hiện từ **Java 7** và vẫn là một công cụ có ích trong **Java hiện đại (Java 17+)**. Không nên hiểu “đã có annotation” đồng nghĩa toàn bộ mã được xác minh an toàn, hoặc annotation đã lỗi thời.

## 2. Cơ chế: vì sao generic varargs có nguy cơ *heap pollution*?

### 2.1. Varargs được xử lý bằng mảng

Xét chữ ký:

```java
static void consume(List<String>... groups) {
    System.out.println(groups.length);
}
```

Bên trong phương thức, `groups` mang dạng mảng; ở mức mã nguồn có thể xem là `List<String>[]`. Khi gọi bằng nhiều đối số rời, compiler thường tạo mảng phù hợp để truyền vào phương thức.

Tuy nhiên, generic trong Java chủ yếu được xử lý bằng **type erasure**: ở runtime, mảng tương ứng được kiểm tra theo kiểu phần tử `List`, chứ không phân biệt phần tử là `List<String>` hay `List<Integer>`. Mảng lại có kiểm tra kiểu runtime theo kiểu phần tử mà nó lưu được. Chính sự kết hợp **mảng reified** với **generic không reifiable** tạo ra khoảng trống an toàn kiểu.

### 2.2. Heap pollution là gì?

*Heap pollution* xảy ra khi một biến có kiểu generic đã tham số hóa giữ tham chiếu tới một đối tượng **không phù hợp với kiểu đã khai báo**, thường thông qua mảng, raw types, ép kiểu unchecked hoặc alias không an toàn.

Ví dụ về nguy cơ:

```java
// Mô tả một phần thân phương thức nhận List<String>... groups.
Object[] alias = groups;
alias[0] = List.of(42);
String name = groups[0].get(0);
```

- `groups` là một mảng các tham chiếu danh sách; có thể gán nó cho biến kiểu `Object[]` theo quan hệ kiểu của mảng.
- Phần tử `List.of(42)` là một `List<Integer>`. Mảng ở runtime vẫn nhận nó vì nó chỉ kiểm tra được đây là một `List`.
- `groups[0].get(0)` được compiler sử dụng như một `String`. Khi giá trị thực tế là `Integer`, chương trình có thể ném `ClassCastException`.

Đây là lỗi **thật ở runtime**, không chỉ là cảnh báo về phong cách. Nguy cơ đặc biệt đáng lưu ý khi thao tác với mảng varargs, biến bí danh kiểu `Object[]`, raw type hoặc việc để tham chiếu mảng thoát ra ngoài phạm vi kiểm soát.

### 2.3. Khác biệt giữa reifiable và non-reifiable

| Kiểu varargs | Vấn đề generic varargs |
| --- | --- |
| `int...` | Không phải varargs của generic non-reifiable |
| `String...` | Kiểu phần tử `String` có thể kiểm tra ở runtime |
| `List<?>...` | `List<?>` là kiểu reifiable theo quy tắc Java, thường không cần `@SafeVarargs` |
| `List<String>...` | Không reifiable; có thể phát sinh cảnh báo unchecked |
| `T...` trong một phương thức generic | `T` thường không reifiable; phải kiểm tra tính an toàn của việc dùng mảng |
| `List<? extends T>...` | Tham số generic lồng wildcard, thường cần đánh giá an toàn tương tự |

Đừng thêm `@SafeVarargs` vô điều kiện cho mọi tham số `...`. Đặt annotation khi có lý do thực tế liên quan đến cảnh báo generic varargs và khi đã đáp ứng **cả điều kiện cú pháp lẫn cam kết an toàn**.

## 3. `@SafeVarargs` chính xác cam kết điều gì?

Về mặt ý nghĩa, người viết phương thức/constructor đang khẳng định:

> Phần triển khai không thực hiện các thao tác có nguy cơ gây heap pollution hoặc phá vỡ an toàn kiểu của biến varargs non-reifiable mà nó nhận được.

Cam kết này thường liên quan đến **cách thân phương thức xử lý mảng varargs**, không chỉ cách khai báo annotation:

- Không dùng alias dạng `Object[]`, raw arrays hay ép kiểu unchecked để đặt vào mảng một phần tử không phù hợp với tham số kiểu đã khai báo.
- Không đưa chính mảng varargs ra nơi khác mà mã không được kiểm soát có thể thay phần tử trái kiểu, rồi tiếp tục dựa vào giả định generic cũ.
- Không chuyển mảng cho callback hoặc API có khả năng ghi vào mảng theo cách phá vỡ kiểu.
- Có thể **đọc từng danh sách và đưa từng phần tử vào một collection kết quả mới** mà không sửa mảng varargs: đây là mẫu điển hình cho một implementation có thể cam kết an toàn.
- Vẫn phải tôn trọng hợp đồng thông thường của đối tượng: danh sách con có thể `null`, code có thể mắc lỗi logic khác, hoặc caller dùng raw types gây lỗi riêng. `@SafeVarargs` không chữa mọi lỗi đó.

**Điều không được cam kết:** annotation không bảo đảm mọi lời gọi đều thành công, không tự chặn `null`, không xác minh immutable/thread-safe, không tạo kiểm tra runtime cho tham số `T` và không tự sửa một phép ép kiểu sai.

Một phương thức có `@SafeVarargs` vẫn có thể bị compiler cảnh báo `[varargs]` **bên trong thân phương thức** khi dùng các tùy chọn lint nghiêm ngặt và thấy thao tác nguy hiểm. Annotation không nhất thiết dập tắt những chẩn đoán này. Đồng thời, compiler **không thể chứng minh mọi kiểu vi phạm trong mọi đường chạy**, nên việc thiếu cảnh báo không thay cho kiểm thử hay review.

## 4. Các cảnh báo được giảm ở đâu?

Xét phương thức không annotation:

```java
import java.util.List;

public final class NoPromise {
    public static void join(List<String>... groups) {
        for (List<String> group : groups) {
            System.out.println(group);
        }
    }

    public static void main(String[] args) {
        join(List.of("a"), List.of("b"));
    }
}
```

Khi biên dịch mã này với tùy chọn:

```bash
javac -Xlint:all -encoding UTF-8 NoPromise.java
```

Trên các JDK hiện đại, bạn có thể gặp **hai vị trí cảnh báo**:

1. **Tại khai báo** `join(List<String>... groups)`: có thể gây heap pollution từ kiểu varargs có tham số.
2. **Tại nơi gọi** `join(List.of("a"), List.of("b"))`: compiler tạo mảng generic varargs cho lời gọi, với thao tác không hoàn toàn được kiểm tra ở runtime.

Mục đích chính của `@SafeVarargs` là để tác giả **đã kiểm chứng implementation** có thể giảm các cảnh báo liên quan ở **khai báo** và **nơi gọi**. Điều này đặc biệt có ích cho API thư viện được nhiều module gọi: người dùng không phải nhìn thấy cùng một cảnh báo unchecked cho một implementation đã được bảo đảm theo hợp đồng.

Phần thân `NoPromise.join` chỉ duyệt và đọc các danh sách nên có thể chuyển sang một API được chú thích an toàn sau khi review:

```java
@SafeVarargs
public static void join(List<String>... groups) {
    for (List<String> group : groups) {
        System.out.println(group);
    }
}
```

Đây là **phần phương thức minh họa**, thuộc một lớp đã import `List`. Không nên giải quyết cảnh báo bằng cách thêm annotation lên bất kỳ phương thức nào mà chưa đọc phần thân hoặc không biết các hàm được gọi có giữ an toàn cho mảng varargs hay không.

## 5. Nơi được phép dùng annotation theo phiên bản Java

`@SafeVarargs` không thể đặt tự do lên mọi phương thức. Lý do cốt lõi: cam kết an toàn chỉ đáng tin nếu một implementation khác **không thể override** phương thức đó rồi phá vỡ cam kết trong khi caller vẫn tin vào annotation.

| Vị trí gắn annotation | Java 7/8 | Java 9+ (bao gồm Java 17+) | Lý do |
| --- | --- | --- | --- |
| Constructor có varargs | Hợp lệ | Hợp lệ | Constructor không bị override |
| Phương thức `static` có varargs | Hợp lệ | Hợp lệ | Phương thức static không bị override theo cơ chế instance |
| Phương thức instance `final` có varargs | Hợp lệ | Hợp lệ | Không thể override |
| Phương thức instance `private` có varargs | Chưa hỗ trợ trường hợp này | Hợp lệ | Java 9 bổ sung, phương thức private không bị override |
| Phương thức instance thông thường có thể override | **Không hợp lệ** | **Không hợp lệ** | Lời cam kết không được bảo toàn qua override |
| Phương thức `abstract` hoặc `default` có thể override | Không hợp lệ | Không hợp lệ | Không phải implementation ổn định theo điều kiện annotation |

### Ví dụ các khai báo hợp lệ

```java
import java.util.ArrayList;
import java.util.List;

class Helper {

    @SafeVarargs
    static <T> List<T> copyAll(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return result;
    }

    @SafeVarargs
    final <T> int count(List<? extends T>... groups) {
        int total = 0;
        for (List<? extends T> group : groups) {
            total += group.size();
        }
        return total;
    }

    // Hợp lệ từ Java 9: private instance method.
    @SafeVarargs
    private <T> void inspect(List<T>... groups) {
        for (List<T> group : groups) {
            System.out.println(group.size());
        }
    }
}
```

Đây là **một lớp Java minh họa**, không có `main`. Mỗi implementation chỉ đọc dữ liệu hoặc sao chép phần tử sang danh sách kết quả mới, không ghi phần tử sai kiểu vào mảng varargs.

Constructor cũng có thể nhận varargs generic:

```java
import java.util.ArrayList;
import java.util.List;

class SafeListBox<T> {
    private final List<T> items = new ArrayList<>();

    @SafeVarargs
    SafeListBox(T... values) {
        for (T value : values) {
            items.add(value);
        }
    }
}
```

Đây là **một lớp độc lập minh họa**: nó giữ các phần tử trong danh sách mới, không lưu mảng varargs vào trường để mã khác sửa mảng. Constructor có thể dùng `@SafeVarargs` dù không có từ khóa `final`.

### Ví dụ không hợp lệ

```java
import java.util.List;

class WrongTarget {
    @SafeVarargs
    public void wrong(List<String>... groups) {
        // Lỗi biên dịch: phương thức instance có thể override
        // không thuộc nhóm mục tiêu hợp lệ.
    }
}
```

Đây là **ví dụ cố ý không biên dịch**. Việc `wrong` có thân rỗng không làm annotation hợp lệ: các ràng buộc của `@SafeVarargs` được kiểm tra độc lập với việc bạn nghĩ implementation hiện tại đã an toàn đến mức nào. Có thể cân nhắc `final` khi thực sự phù hợp với thiết kế kế thừa, hoặc dùng phương thức `private` trên Java 9+, thay vì tự ý khóa phương thức public chỉ để né cảnh báo.

> Ghi chú phiên bản: `@SafeVarargs` ra đời từ Java 7; khả năng dùng trên **private instance methods** được bổ sung ở Java 9. `List.of` được dùng ở một số ví dụ Java 17+ và cũng là API có từ Java 9; vì vậy không nên sao chép nguyên các ví dụ sử dụng `List.of` rồi giả định chúng chạy nguyên trạng trên JDK 7.

## 6. Một implementation có thể cam kết an toàn: không sửa hoặc làm rò mảng

Một mẫu sử dụng hợp lý là ghép các danh sách thành một `ArrayList` mới. Trong cách này:

- Mảng varargs chỉ dùng để **duyệt** từng danh sách.
- Không gán lại các phần tử của mảng `groups`.
- Không đưa mảng `groups` ra ngoài (không lưu vào trường, không trả nó như một đối tượng cho caller sửa).
- Không dùng `Object[]` hay raw type để vượt kiểm tra kiểu.
- Kết quả là một collection mới chứa các phần tử được đọc theo kiểu `T` phù hợp.

```java
@SafeVarargs
public static <T> List<T> flatten(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

Đoạn trên là **phần phương thức** và cần import `List`, `ArrayList`; lớp chạy độc lập ở mục 7.

Tại sao khai báo `List<? extends T>` thay vì `List<T>`? Vì phương thức chỉ **đọc phần tử từ từng danh sách nguồn** để thêm vào kết quả; wildcard `? extends T` cho phép nhận các danh sách mang kiểu con thích hợp. Tuy nhiên, annotation vẫn cần cho generic varargs khi phần tử mảng là loại không reifiable. Wildcard không tự xóa đi mọi rủi ro varargs.

Hãy đọc `@SafeVarargs` như một hợp đồng mà **từng implementation cụ thể phải duy trì**: nếu sau này refactor phương thức để lưu mảng vào trạng thái toàn cục, chuyển nó tới một hàm có thể sửa, hoặc tạo alias `Object[]` rồi ghi dữ liệu không tương thích, cam kết ban đầu phải được đánh giá lại.

## 7. Ví dụ Java 17+ hoàn chỉnh, có thể biên dịch và chạy

Chương trình dùng cùng một kiểu generic varargs qua các ngữ cảnh hợp lệ: phương thức `static`, phương thức `private static` và phương thức instance `final`. Chúng chỉ đọc danh sách nguồn, tính tổng hoặc tạo danh sách kết quả mới.

Tạo tệp **`SafeVarargsPromiseDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class SafeVarargsPromiseDemo {

    @SafeVarargs
    public static <T> List<T> flatten(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return result;
    }

    @SafeVarargs
    private static <T> int sizeSum(List<? extends T>... groups) {
        int sum = 0;
        for (List<? extends T> group : groups) {
            sum += group.size();
        }
        return sum;
    }

    static final class Collector {
        @SafeVarargs
        public final <T> List<T> combine(List<? extends T>... groups) {
            List<T> result = new ArrayList<>();
            for (List<? extends T> group : groups) {
                result.addAll(group);
            }
            return result;
        }
    }

    public static void main(String[] args) {
        List<String> first = List.of("An", "Binh");
        List<String> second = List.of("Chi");

        System.out.println("names = " + flatten(first, second));
        System.out.println("total = " + sizeSum(first, second));
        System.out.println("collector = "
                + new Collector().combine(first, second));
        System.out.println("numbers = "
                + flatten(List.of(1, 2), List.of(3)));
    }
}
```

Biên dịch ở chế độ kiểm tra chặt và chạy với JDK 17+:

```bash
javac -Xlint:all -Werror -encoding UTF-8 SafeVarargsPromiseDemo.java
java SafeVarargsPromiseDemo
```

Tùy chọn `-Xlint:all` bật nhóm cảnh báo của compiler, còn `-Werror` làm lệnh biên dịch thất bại nếu có cảnh báo. Trong ví dụ này, cách dùng varargs đã được kiểm tra để không có cảnh báo khi biên dịch bằng lệnh trên.

**Stdout chính xác:**

```text
names = [An, Binh, Chi]
total = 3
collector = [An, Binh, Chi]
numbers = [1, 2, 3]
```

Giải thích:

1. `flatten(first, second)` nhận hai `List<String>`, duyệt chúng và tạo một `ArrayList<String>` mới.
2. `sizeSum` duyệt mảng varargs chỉ để đọc kích thước, không trả hoặc sửa mảng.
3. `Collector.combine` là phương thức instance `final` nên đáp ứng điều kiện vị trí của annotation; kết quả hợp nhất giữ thứ tự phần tử đã thêm.
4. `flatten(List.of(1, 2), List.of(3))` suy luận `T` thích hợp với `Integer` và trả danh sách số.
5. Annotation không làm các phần tử của danh sách nguồn bất biến. `List.of` là phương thức factory tạo danh sách không cho phép sửa, nhưng tính chất đó **đến từ `List.of`**, không phải `@SafeVarargs`.
6. Chương trình chạy ở Java 17+; `List.of` chỉ có từ Java 9 trở lên, còn `@SafeVarargs` và quy tắc với `static`/`final` đã có từ Java 7.

## 8. Vi phạm cam kết: có annotation nhưng vẫn gây `ClassCastException`

Đây là phần bắt buộc hiểu trước khi đưa `@SafeVarargs` vào mã thư viện: annotation là một **lời hứa có thể bị viết sai**. Compiler không tự thêm một cơ chế chống heap pollution vào runtime.

Tạo một tệp riêng **`UnsafePromiseDemo.java`**:

```java
import java.util.List;

public final class UnsafePromiseDemo {

    @SafeVarargs
    public static void broken(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(42);

        // Compiler tin groups[0] chứa String nhưng thực tế là Integer.
        String value = groups[0].get(0);
        System.out.println(value);
    }

    public static void main(String[] args) {
        try {
            broken(List.of("safe"));
        } catch (ClassCastException ex) {
            System.out.println("caught ClassCastException");
        }
    }
}
```

Biên dịch với kiểm tra các thao tác varargs nguy hiểm:

```bash
javac -Xlint:varargs -encoding UTF-8 UnsafePromiseDemo.java
java UnsafePromiseDemo
```

Compiler có thể đưa ra cảnh báo `[varargs]` ngay tại `Object[] alias = groups;` do mảng varargs có nguy cơ heap pollution; phiên bản JDK và tùy chọn lint quyết định cách trình bày chẩn đoán. **Stdout khi chạy:**

```text
caught ClassCastException
```

Điều gì đã xảy ra?

1. `@SafeVarargs` giúp giảm cảnh báo unchecked ở khai báo/nơi gọi, **nhưng không biến thao tác alias thành an toàn**.
2. Mảng chứa các đối tượng `List` được nhìn qua `Object[]`; gán `List<Integer>` vào ô vốn được mã nguồn giả định là `List<String>`.
3. Khi Java phải dùng phần tử đọc ra như `String`, giá trị runtime là `Integer` và gây `ClassCastException`.
4. Ví dụ được viết **cố ý không an toàn để học**. Không sao chép pattern này vào ứng dụng hoặc thêm `@SafeVarargs` để bỏ qua cảnh báo.

Một cách khắc phục đúng là **không viết vào mảng varargs** hoặc đưa mảng cho mã có thể làm vậy; nếu cần dựng dữ liệu mới, hãy tạo container riêng như ở `flatten`. Xóa annotation khỏi phương thức nguy hiểm giúp các cảnh báo unchecked tại khai báo/nơi gọi xuất hiện lại, nhưng **không tự sửa bản chất bug**.

## 9. Phân biệt `@SafeVarargs` với `@SuppressWarnings("unchecked")`

Đây là hai công cụ phục vụ những mục đích khác nhau:

| Khía cạnh | `@SafeVarargs` | `@SuppressWarnings("unchecked")` |
| --- | --- | --- |
| Ý nghĩa | Lời cam kết rằng phần triển khai varargs không làm thao tác generic varargs không an toàn | Yêu cầu compiler bỏ cảnh báo `unchecked` trong phạm vi được đánh dấu |
| Vị trí | Chỉ constructor và một số phương thức có varargs, theo quy tắc Java | Nhiều vị trí khai báo/phạm vi hợp lệ tùy target annotation |
| Phạm vi cảnh báo | Đặc biệt liên quan đến generic varargs ở khai báo và nơi gọi | Cảnh báo unchecked trong phạm vi áp dụng; không mang hợp đồng varargs riêng |
| Người dùng API có được hưởng không? | Có thể tránh cảnh báo generic varargs tại call site | Không tự tạo lời cam kết tại mọi call site của API |
| Compiler có bảo đảm implementation an toàn không? | Không | Không |
| Thay thế việc review an toàn kiểu? | Không | Không |

Không nên gắn cả hai annotation để “dập sạch” cảnh báo mà không hiểu nguồn gốc. Nếu phải làm việc với raw types hoặc ép kiểu unchecked không tránh được, hãy cô lập phép chuyển đổi, kiểm tra hợp đồng dữ liệu, giải thích lý do và đặt phạm vi suppression nhỏ. `@SafeVarargs` chỉ dành cho tình huống **thực sự có varargs kiểu không reifiable và implementation giữ được cam kết**.

### Đừng nhầm với `@Override` hoặc `final`

- `@Override` xác nhận một phương thức đang override một phương thức khác; không liên quan trực tiếp đến varargs an toàn.
- `final` trên phương thức ngăn override, giúp **đủ điều kiện vị trí** cho `@SafeVarargs`; nó không tự làm phần thân phương thức an toàn.
- `private` trên phương thức instance Java 9+ cũng là một điều kiện vị trí hợp lệ, nhưng vẫn phải kiểm tra logic nội bộ.
- `@SafeVarargs` không tự biến đối số được truyền thành immutable, không thêm ràng buộc `final` cho tham số array và không thay đổi cách Java áp dụng generics ở runtime.

## 10. Các trường hợp thực tế nên cân nhắc trước khi chú thích

### 10.1. Mảng varargs có thoát khỏi phương thức không?

Hãy rà soát việc lưu, trả về hoặc chia sẻ **chính mảng varargs**:

```java
// Minh họa một pattern có nguy cơ, đặt trong lớp phù hợp.
static <T> T[] expose(T... values) {
    return values;
}
```

Ở đây mảng đầu vào có thể “thoát” ra caller. Kết hợp suy luận kiểu generic với mảng do compiler tạo có thể gây rủi ro kiểu ở ranh giới API. Không được tự kết luận phương thức này an toàn chỉ vì không thấy lời gán `values[i] = ...` trong phần thân. Đối với API danh sách, cân nhắc tạo bản sao có kiểu rõ ràng hoặc trả `List<T>` phù hợp thay vì trả mảng varargs mà người dùng có thể sửa.

Trong trường hợp mục tiêu chỉ gom phần tử, ví dụ minh họa:

```java
@SafeVarargs
static <T> List<T> toList(T... values) {
    List<T> result = new ArrayList<>();
    for (T value : values) {
        result.add(value);
    }
    return result;
}
```

Đây là **đoạn phương thức**, yêu cầu import `List`/`ArrayList`. Nó trả một danh sách mới và không chia sẻ mảng varargs ra ngoài. Lưu ý: các phần tử đối tượng được sao chép **theo tham chiếu**, không deep copy.

### 10.2. Có alias, raw type hoặc unchecked cast không?

Rà soát các dấu hiệu đáng ngờ:

```java
Object[] alias = groups;
```

```java
// Phác thảo nguy cơ: ép kiểu mảng không an toàn hoặc raw array.
List[] raw = groups;
```

Đây là **các câu lệnh minh họa trong phương thức có `groups` là `List<String>...`**. Các kiểu quá rộng có thể cho phép thêm phần tử không phù hợp vào mảng. Không phải mọi alias đều lập tức gây lỗi, nhưng việc gắn annotation yêu cầu tác giả **chứng minh** không có thao tác nguy hiểm theo đường truyền dữ liệu.

### 10.3. Phương thức có thể được override không?

Nếu method có thể override, không dùng `@SafeVarargs` để hứa an toàn cho các implementation chưa biết. Một lựa chọn là thay API bằng phương thức `static` hoặc `final` phù hợp thiết kế; lựa chọn khác là nhận một collection bình thường thay vì varargs để không cần annotation.

### 10.4. Có cần varargs thật không?

Nếu caller vốn đã có `List<List<T>>`, một API nhận collection các danh sách có thể rõ ràng hơn:

```java
static <T> List<T> flattenNested(
        List<? extends List<? extends T>> groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

Đây là **phương thức minh họa** thuộc lớp có import `List`/`ArrayList`. Không sử dụng varargs ở tham số, nên tránh riêng loại cảnh báo tạo mảng generic varargs. Tuy nhiên nó vẫn phải xử lý dữ liệu đầu vào và hợp đồng generic đúng cách. Chọn phương án này khi API sử dụng đầu vào dạng tập hợp là tự nhiên; không bắt người gọi tự tạo list lồng nhau chỉ để né một annotation đã được kiểm chứng an toàn.

## 11. Checklist review cho `@SafeVarargs`

Trước khi đánh dấu một API an toàn, kiểm tra các câu hỏi sau:

1. **Loại tham số:** phương thức/constructor có thực sự dùng `...` với kiểu không reifiable như `T...`, `List<String>...` hoặc `List<? extends T>...` không?
2. **Vị trí hợp lệ:** đây là constructor, phương thức `static`, `final`, hoặc `private` (trong Java 9+) chứ không phải phương thức instance overridable?
3. **Mảng varargs:** implementation có ghi vào mảng bằng alias, raw types hoặc ép kiểu không an toàn hay không?
4. **Thoát tham chiếu:** mảng varargs có bị lưu vào field, trả ra ngoài hoặc đưa cho API có thể làm mất an toàn kiểu không?
5. **Hành vi của helper:** phương thức gọi xuống có giữ bất biến kiểu của phần tử không, hay thao tác ngầm trên mảng?
6. **Chỉ tắt đúng cảnh báo:** có cảnh báo `[varargs]`/`[unchecked]` nào vẫn báo trong body không, và mỗi cảnh báo đó đã được giải quyết bằng code hay lý do vững chắc chưa?
7. **Kiểm thử:** có test cho nhiều đối số, một đối số, mảng truyền trực tiếp, generic type khác nhau và các trường hợp dữ liệu `null` theo hợp đồng?
8. **Hợp đồng API:** nếu implementation sửa đổi sau này, quy trình review có nhắc kiểm tra lại `@SafeVarargs` không?

Kiểm tra với compiler:

```bash
javac -Xlint:all -Werror -encoding UTF-8 SafeVarargsPromiseDemo.java
```

Tùy chọn này giúp phát hiện nhiều vấn đề tiềm ẩn, **nhưng không phải chứng minh hình thức về an toàn kiểu**. Các công cụ phân tích tĩnh, test và review nguồn vẫn quan trọng.

## 12. Lỗi thường gặp và cách sửa

| Nhầm lẫn | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Có `@SafeVarargs` nghĩa là compiler đã kiểm tra mọi thao tác trong phương thức.” | Annotation là lời khẳng định của programmer; vẫn có thể có heap pollution | Review alias/ghi mảng/array escape, kiểm thử và dùng lint |
| Dùng `@SafeVarargs` trên phương thức instance không `final` hoặc `private` | Không thuộc target hợp lệ | Đổi thiết kế API hoặc không dùng annotation |
| Dùng `@SafeVarargs` trên phương thức `private` của Java 7/8 | Java 9 mới cho phép private instance method | Dựa vào quy tắc phiên bản dự án |
| Cho rằng generic varargs vẫn giữ `String` trong mảng lúc runtime | Type erasure làm mất phần kiểm tra đối số kiểu | Tránh thao tác alias/ghi mảng không an toàn |
| Trộn `List<Integer>` vào `List<String>...` qua `Object[]` | Heap pollution và `ClassCastException` | Không sửa mảng varargs qua alias rộng |
| Nghĩ annotation tự động làm `List.of`/collection bất biến | Không liên quan mutability | Phân biệt hợp đồng factory collection với annotation |
| Gọi `@SuppressWarnings("unchecked")` thay cho hợp đồng varargs | Không diễn đạt lời cam kết ở API call site | Chọn annotation đúng nếu thực sự an toàn |
| Bỏ qua warning `-Xlint:varargs` còn xuất hiện trong body | Có thể đang có thao tác đáng ngờ | Kiểm tra warning, xử lý nguyên nhân thay vì che |
| Trả trực tiếp mảng generic varargs mà không đánh giá hậu quả | Có thể làm lộ mảng được tạo ở call site | Cân nhắc tạo bản sao/container riêng |
| Chỉ thêm `final` để annotation hợp lệ | `final` không đảm bảo an toàn logic | Kiểm tra phương thức không gây heap pollution |
| Đánh đồng “không có cảnh báo” với “không có lỗi runtime” | Nhiều lỗi khác vẫn có thể xảy ra | Kiểm thử và xử lý dữ liệu theo hợp đồng |

## 13. Bài tập tự luyện và đáp án

### Bài 1 — Nhận diện lời cam kết

```java
@SafeVarargs
static <T> List<T> copy(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

**Câu hỏi:** Annotation cam kết điều gì? Vì sao ví dụ có khả năng đáp ứng?

**Đáp án:** Tác giả khẳng định phần triển khai không thực hiện thao tác nguy hiểm trên mảng varargs non-reifiable. Mã chỉ duyệt và sao chép các phần tử sang một `ArrayList` mới, không gán lại phần tử mảng hoặc đưa mảng cho mã có thể sửa nó. Đó là mẫu sử dụng an toàn thường gặp, nhưng vẫn cần theo dõi khi sửa implementation.

### Bài 2 — Phương thức nào không hợp lệ?

```java
class Service {
    @SafeVarargs
    void process(List<String>... values) {
    }
}
```

**Câu hỏi:** Có biên dịch trên Java 17 không?

**Đáp án:** Không. `process` là phương thức instance có thể override; không `final` và không `private`. `@SafeVarargs` không hợp lệ tại vị trí này, dù phần thân hiện tại rỗng.

### Bài 3 — Hai cảnh báo unchecked

**Câu hỏi:** Vì sao một phương thức không có `@SafeVarargs` nhận `List<String>...` có thể cảnh báo ở **cả khai báo và nơi gọi**?

**Đáp án:** Kiểu `List<String>` không reifiable, trong khi varargs dựa vào mảng. Compiler cần cảnh báo rằng tạo và truyền mảng generic varargs có thể gây heap pollution. `@SafeVarargs` chỉ phù hợp nếu tác giả đã xác minh implementation an toàn.

### Bài 4 — Heap pollution

```java
@SafeVarargs
static void broken(List<String>... groups) {
    Object[] a = groups;
    a[0] = List.of(123);
    String s = groups[0].get(0);
}
```

**Câu hỏi:** Điều gì sai? Annotation có ngăn lỗi không?

**Đáp án:** Alias `Object[]` cho phép đặt `List<Integer>` vào mảng mà mã nguồn giả định chứa `List<String>`. Đọc phần tử như `String` có thể gây `ClassCastException`. Annotation không tự ngăn lỗi, mà bị dùng sai cam kết.

### Bài 5 — Java 7 và Java 9

**Câu hỏi:** Phương thức instance `private` gắn `@SafeVarargs` hợp lệ từ phiên bản nào? Phương thức `static` và constructor thì sao?

**Đáp án:** Private instance method được chấp nhận từ **Java 9**. Static method, final instance method và constructor đã thuộc nhóm vị trí hợp lệ từ **Java 7**. Trong mọi trường hợp cần có varargs và nội dung phải thực sự an toàn.

### Bài 6 — Dùng `@SuppressWarnings` thay có được không?

**Câu hỏi:** Nếu gắn `@SuppressWarnings("unchecked")` cho thân một phương thức, có tương đương lời cam kết của `@SafeVarargs` cho mọi caller không?

**Đáp án:** Không. `@SuppressWarnings` bỏ qua cảnh báo trong phạm vi chỉ định; nó không biểu thị hợp đồng chuyên biệt rằng cách xử lý generic varargs của API an toàn để compiler giảm cảnh báo ở các nơi gọi như `@SafeVarargs`.

### Bài 7 — Chọn thiết kế API

**Câu hỏi:** Khi nào nên nhận `List<? extends List<? extends T>>` thay vì `List<? extends T>...`?

**Đáp án:** Khi người gọi đã có một collection chứa các collection và việc tiếp nhận chúng theo cấu trúc đó phù hợp nghiệp vụ. Dạng tham số không varargs tránh riêng nguy cơ/cảnh báo do tạo mảng generic varargs. Nếu caller muốn truyền nhiều danh sách rời và implementation đã an toàn, một API varargs được chú thích đúng vẫn là lựa chọn hợp lệ.

## 14. Tổng kết

`@SafeVarargs` là một **cam kết rõ ràng của tác giả API**, không phải “bùa” tắt cảnh báo để chạy qua compiler. Nó có ý nghĩa khi phương thức hoặc constructor nhận varargs của kiểu generic không reifiable và **thực sự không làm phát sinh thao tác heap pollution không an toàn** trên tham số đó. Compiler dựa vào cam kết để giảm cảnh báo ở khai báo và nơi gọi; nhưng người viết mã phải giữ cam kết bằng thiết kế, kiểm thử và review.

Từ Java 7 đến Java hiện đại, các vị trí hợp lệ chủ yếu là **constructor**, **phương thức static**, **phương thức final** và (từ Java 9) **phương thức private**. Không dùng annotation trên phương thức instance có thể override. Hãy đọc/ghép dữ liệu theo kiểu an toàn, tránh ghi mảng qua alias rộng hoặc làm lộ mảng varargs, và không che khuất cảnh báo `[varargs]` liên quan đến code nguy hiểm.