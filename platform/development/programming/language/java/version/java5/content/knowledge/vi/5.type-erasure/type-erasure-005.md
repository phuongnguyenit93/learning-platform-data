# Trùng chữ ký phương thức sau khi xóa kiểu

## 1. Vấn đề: nhìn khác ở mã nguồn nhưng không tạo được hai overload

Giả sử cần hai cách xử lý danh sách: một dành cho tên người, một dành cho điểm số. Ta có thể nghĩ tới hai phương thức cùng tên:

```java
import java.util.List;

class BrokenProcessor {
    void process(List<String> values) {
    }

    void process(List<Integer> values) {
    }
}
```

Đây là ví dụ **cố ý không biên dịch**.

Hai tham số ở mã nguồn khác nhau ở `String` và `Integer`. Nhưng khi xóa kiểu:

```text
process(List<String>)  -> process(List)
process(List<Integer>) -> process(List)
```

Cả hai khai báo cố tạo các phương thức cùng tên với cùng dãy kiểu tham số sau xóa. Trình biên dịch báo lỗi thường chứa cụm:

```text
name clash
have the same erasure
```

Đây là lỗi tại lúc biên dịch, không phải một ngoại lệ khi chạy. Nó xảy ra ngay cả khi chưa có lời gọi nào tới `process`.

Kiến thức này vẫn áp dụng trong Java hiện nay. Bài sử dụng mã có thể kiểm tra bằng JDK 17 trở lên; các ví dụ cố ý lỗi được đánh dấu riêng.

## 2. Chữ ký ở Java khác descriptor của JVM

Ở mức thiết kế API, cần phân biệt ba lớp thông tin:

| Lớp thông tin | Vai trò |
| --- | --- |
| Chữ ký phương thức theo ngôn ngữ Java | Dùng các quy tắc về tên, tham số kiểu và kiểu tham số để xác định overload, subsignature và override |
| Chữ ký sau xóa kiểu | Bỏ hoặc thay thông tin generic theo quy tắc erasure để đánh giá các quan hệ liên quan |
| Descriptor trong class file | Biểu diễn kiểu tham số và kiểu kết quả dùng ở mức JVM |

Đối với hai phương thức `process` phía trên, tham số `List<String>` và `List<Integer>` đều xóa về `List`. Nếu cả hai cùng trả `void`, descriptor dự kiến đều là:

```text
(Ljava/util/List;)V
```

Tuy nhiên, **không được suy ra rằng chỉ cần đổi kiểu trả về là khai báo hợp lệ**. Trong ngôn ngữ Java, kiểu trả về không phải tiêu chí để phân biệt hai overload có cùng tên và dãy tham số.

JVM descriptor có chứa kiểu kết quả, nhưng quy tắc khai báo phương thức của Java vẫn phải được tuân thủ. Không nên dùng cách nói “JVM không bao giờ nhìn kiểu trả về” để giải thích lỗi overload; hai khái niệm này khác nhau.

Quy tắc chữ ký và quan hệ giữa chúng được định nghĩa trong [JLS: Method Signature](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.2).

## 3. Cách tính nhanh kiểu bị xóa

Khi kiểm tra một cặp phương thức, trước hết đổi từng kiểu tham số sang dạng sau xóa:

| Kiểu tham số ở mã nguồn | Kiểu sau xóa |
| --- | --- |
| `List<String>` | `List` |
| `List<Integer>` | `List` |
| `List<?>` | `List` |
| `List<? extends Number>` | `List` |
| `Map<String, Integer>` | `Map` |
| `T` trong `<T>` | `Object` |
| `T` trong `<T extends Number>` | `Number` |
| `T[]` trong `<T>` | `Object[]` |

Sau đó so sánh **tên phương thức và toàn bộ dãy tham số theo thứ tự**.

Ví dụ:

```text
send(List<String>, int)    -> send(List, int)
send(List<Integer>, long)  -> send(List, long)
```

Hai dãy này còn khác ở `int` và `long` nên không có xung đột giống ví dụ đầu. Điều đó chỉ chứng minh một điều kiện về khai báo; việc từng lời gọi có chọn được overload rõ ràng hay không vẫn cần kiểm tra riêng.

Với tham số kiểu có giới hạn, phải dùng giới hạn trái nhất thay vì thay mọi thứ bằng `Object`. Xem [JLS: Type Erasure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6).

## 4. Các dạng trùng chữ ký thường gặp

### 4.1. Khác đối số kiểu của cùng một kiểu generic

Các cặp sau đều không thể khai báo như hai overload trong cùng lớp:

```java
// void save(List<String> values) {}
// void save(List<Long> values) {}

// void merge(java.util.Map<String, Integer> values) {}
// void merge(java.util.Map<Integer, String> values) {}
```

Các dòng được chú thích vì đây là những cặp minh họa không hợp lệ. Đảo thứ tự đối số kiểu của `Map` không đổi kiểu sau xóa của tham số: cả hai vẫn là `Map`.

### 4.2. Wildcard không giữ lại một loại tham số runtime khác

```java
// void inspect(List<? extends Number> values) {}
// void inspect(List<? super Integer> values) {}
```

Giới hạn wildcard tác động tới những đối số và thao tác được chấp nhận ở mã nguồn. Nó không tạo hai kiểu danh sách riêng trong descriptor: cả hai vẫn xóa về `List`.

Đổi `List<String>` thành `List<?>` cũng không tự chữa được một cặp phương thức cùng tên nhận `List` sau xóa.

### 4.3. Phương thức generic và phương thức không generic

Đây là lớp cố ý không biên dịch:

```java
class BoundClash {
    <T extends Number> void accept(T value) {
    }

    void accept(Number value) {
    }
}
```

`T` xóa về `Number`. Vì vậy, cả hai có dạng tham số sau xóa là `accept(Number)`.

Không phải chỉ khi cả hai phương thức đều có dấu `<...>` mới có nguy cơ xung đột.

### 4.4. Đổi tên T thành U không tạo phương thức mới

Tên tham số kiểu là tên cục bộ của khai báo. Hai phương thức như `<T> void run(T value)` và `<U> void run(U value)` không trở thành hai overload chỉ vì tên `T` và `U` khác nhau.

Tương tự, đổi tên biến `value` thành `item` hoàn toàn không tham gia phân biệt overload.

### 4.5. Kiểu trả về khác nhau không sửa được xung đột

Lớp sau cố ý không biên dịch:

```java
import java.util.List;

class ResultClash {
    int read(List<String> values) {
        return values.size();
    }

    String read(List<Integer> values) {
        return values.toString();
    }
}
```

Hai phương thức có cùng tên và cùng tham số sau xóa `List`. Người gọi viết `read(...)` không có quyền chọn overload chỉ dựa trên việc muốn nhận `int` hay `String`.

Thay `throws`, mức truy cập, annotation hoặc đổi một phương thức thành `static` cũng không tạo ra khác biệt cần thiết trong dãy tham số.

## 5. Xung đột trong kế thừa: không phải mọi cùng erasure đều là override

Xét lớp cha generic và lớp con sau. Toàn bộ ví dụ này cố ý không biên dịch:

```java
class Parent<T> {
    void save(T value) {
    }
}

class WrongChild extends Parent<String> {
    void save(Object value) {
    }
}
```

Ở góc nhìn của `WrongChild`, phương thức kế thừa có tham số `String` do `T` được thay bằng `String`. `save(Object)` do lớp con khai báo không phải cách ghi đè đúng phương thức `save(String)` đó.

Đồng thời, khai báo `Parent.save(T)` có tham số bị xóa thành `Object`. Kết quả là một xung đột mà trình biên dịch thường mô tả bằng cụm:

```text
have the same erasure, yet neither overrides the other
```

Cần đọc cả hai vế: cùng dạng sau xóa **và không có quan hệ override hợp lệ**. Không nên rút gọn thành quy tắc “mọi phương thức kế thừa cùng erasure đều bị cấm”. Ghi đè hợp lệ trong hệ generic vẫn tồn tại.

Bản đúng:

```java
class GenericParent<T> {
    void save(T value) {
    }
}

class CorrectChild extends GenericParent<String> {
    @Override
    void save(String value) {
    }
}
```

`@Override` giúp xác minh mục đích ghi đè tại lúc biên dịch. Trong trường hợp này, `javac` sinh phương thức cầu nối (bridge method) nhận `Object` để duy trì lời gọi đa hình theo biểu diễn đã xóa.

Phương thức cầu nối là chi tiết do trình biên dịch sinh, không phải lý do để ta tự thêm `save(Object)` cạnh `save(String)` trong lớp con. Xung đột với cầu nối là một trong những lý do không nên tự “mô phỏng bytecode” bằng các khai báo bổ sung thiếu quan hệ kiểu phù hợp.

Các điều kiện liên quan tới kế thừa được nêu ở [JLS: Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.3).

## 6. Những overload nào vẫn hợp lệ?

### 6.1. Khác kiểu chứa thực sự

```java
static int sizeOf(List<?> values) {
    return values.size();
}

static int sizeOf(java.util.Set<?> values) {
    return values.size();
}
```

Hai khai báo minh họa hợp lệ trong một lớp có import `java.util.List`. Sau xóa, một bên là `List`, bên kia là `Set`.

Tuy nhiên, nếu cần cùng một hành vi cho mọi tập hợp, một phương thức nhận `Collection<?>` có thể đơn giản hơn. Chỉ chia overload khi sự phân biệt loại chứa có ý nghĩa đối với API.

### 6.2. Giới hạn đầu khác nhau tạo kiểu xóa khác nhau

```java
static <T extends Number> String kind(T value) {
    return "number";
}

static <T extends CharSequence> String kind(T value) {
    return "text";
}
```

Cặp này hợp lệ: tham số sau xóa là `Number` và `CharSequence`.

Nhưng không nên thêm giới hạn tùy tiện chỉ để tránh lỗi. Giới hạn là một phần hợp đồng, quyết định ai gọi được phương thức. Nếu nghiệp vụ không có điều kiện tương ứng, cách sửa ấy làm API khó hiểu.

### 6.3. Khác một tham số có ý nghĩa

Thêm một tham số chính sách hoặc một đối tượng yêu cầu thực sự có thể tạo API hợp lệ. Ví dụ, truyền bộ định dạng giúp một phương thức generic duy nhất xử lý nhiều kiểu phần tử.

Ngược lại, thêm một `boolean` không được dùng hoặc một tham số đánh dấu phải truyền `null` chỉ để “lách erasure” khiến lời gọi khó đọc và không mô tả đúng nghiệp vụ.

### 6.4. Khai báo hợp lệ chưa chắc mọi lời gọi đều rõ ràng

Với hai overload `sizeOf(List<?>)` và `sizeOf(Set<?>)`, lời gọi `sizeOf(null)` bị mơ hồ: `null` phù hợp với cả hai kiểu không có quan hệ kiểu con trực tiếp để chọn một bên.

Đây là **lỗi phân giải overload ở lời gọi**, khác với **xung đột khai báo sau xóa kiểu**. Hãy xác định lỗi nằm ở giai đoạn nào trước khi sửa.

## 7. Ba cách thiết kế lại API theo ý nghĩa của tác vụ

### Cách 1: Đổi tên theo hành vi

Nếu xử lý tên và tính tổng điểm là hai việc khác nhau, dùng tên phản ánh mục đích:

```java
static String summarizeNames(List<String> values) {
    return String.join(", ", values);
}

static int sumScores(List<Integer> values) {
    return values.stream().mapToInt(Integer::intValue).sum();
}
```

Không cần buộc chúng dùng chung tên `process`. Kiểu trả về khác nhau ở đây thể hiện hai tác vụ khác nhau; tên riêng giúp người gọi hiểu sự khác biệt trực tiếp.

### Cách 2: Dùng một phương thức generic và truyền hành vi

Nếu cấu trúc thuật toán là duyệt từng phần tử rồi định dạng, có thể khai báo:

```java
static <T> String render(
        List<T> values,
        java.util.function.Function<? super T, String> formatter)
```

Chỉ có **một** khai báo generic, sử dụng cho nhiều kiểu `T`. `formatter` quyết định cách chuyển một phần tử thành văn bản, thay vì tạo một overload cho mỗi đối số kiểu của `List`.

Đây là chữ ký minh họa; phần triển khai có trong chương trình đầy đủ bên dưới.

### Cách 3: Tạo kiểu thể hiện khái niệm nghiệp vụ

`Names` và `Scores` có thể là hai record chứa các danh sách tương ứng. Hai kiểu record khác nhau vẫn là hai kiểu tham số khác nhau sau xóa:

```text
describe(Names)
describe(Scores)
```

Cách này hữu ích nếu hai tập dữ liệu có ý nghĩa và quy tắc kiểm tra riêng. Không nên tạo hàng loạt lớp bọc chỉ để giữ một tên phương thức khi đổi tên đã đủ rõ.

## 8. Chương trình đầy đủ: các phương án đúng chạy được

Lưu thành `ErasureClashDemo.java`:

```java
import java.util.List;
import java.util.Set;
import java.util.StringJoiner;
import java.util.function.Function;

public class ErasureClashDemo {
    record Names(List<String> values) {
        Names {
            values = List.copyOf(values);
        }
    }

    record Scores(List<Integer> values) {
        Scores {
            values = List.copyOf(values);
        }
    }

    static String summarizeNames(List<String> values) {
        return String.join(", ", values);
    }

    static int sumScores(List<Integer> values) {
        return values.stream().mapToInt(Integer::intValue).sum();
    }

    static <T> String render(
            List<T> values,
            Function<? super T, String> formatter) {
        StringJoiner result = new StringJoiner(" | ");
        for (T value : values) {
            result.add(formatter.apply(value));
        }
        return result.toString();
    }

    static String describe(Names names) {
        return "names: " + summarizeNames(names.values());
    }

    static String describe(Scores scores) {
        return "scores total: " + sumScores(scores.values());
    }

    static String containerKind(List<?> values) {
        return "list size: " + values.size();
    }

    static String containerKind(Set<?> values) {
        return "set size: " + values.size();
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        List<Integer> scores = List.of(7, 8);

        System.out.println(summarizeNames(names));
        System.out.println(sumScores(scores));
        System.out.println(render(names, value -> "[" + value + "]"));
        System.out.println(render(scores, value -> "score=" + value));

        System.out.println(describe(new Names(names)));
        System.out.println(describe(new Scores(scores)));
        System.out.println(containerKind(names));
        System.out.println(containerKind(Set.of("An", "Binh")));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all ErasureClashDemo.java
java ErasureClashDemo
```

Stdout:

```text
An, Binh
15
[An] | [Binh]
score=7 | score=8
names: An, Binh
scores total: 15
list size: 2
set size: 2
```

Những điều cần quan sát:

- `summarizeNames` và `sumScores` có tên khác nhau vì tác vụ khác nhau.
- `render` là một khai báo duy nhất dùng với cả `String` lẫn `Integer`.
- Hai overload `describe` nhận hai record khác nhau; chúng không chỉ khác đối số kiểu của `List`.
- Hai overload `containerKind` nhận `List` và `Set`, nên kiểu sau xóa vẫn khác nhau.
- Các record tạo ảnh chụp danh sách bằng `List.copyOf`. Đầu vào và các phần tử phải khác `null`; đây là hợp đồng của ví dụ.
- Chương trình không phân nhánh bằng cách đọc kiểu của phần tử đầu tiên, nên vẫn thiết kế được cho danh sách rỗng.

`sumScores` dùng `int` cho ví dụ số điểm nhỏ. Trong nghiệp vụ có thể vượt phạm vi `int`, cần chọn kiểu và chính sách kiểm tra tràn phù hợp riêng.

## 9. Xác minh dạng sau xóa bằng javap

Sau khi biên dịch chương trình đúng:

```shell
javap -p -s ErasureClashDemo
```

Tìm các descriptor:

```text
summarizeNames:
    (Ljava/util/List;)Ljava/lang/String;

sumScores:
    (Ljava/util/List;)I

render:
    (Ljava/util/List;Ljava/util/function/Function;)Ljava/lang/String;

describe voi Names:
    (LErasureClashDemo$Names;)Ljava/lang/String;

describe voi Scores:
    (LErasureClashDemo$Scores;)Ljava/lang/String;

containerKind voi List:
    (Ljava/util/List;)Ljava/lang/String;

containerKind voi Set:
    (Ljava/util/Set;)Ljava/lang/String;
```

Khối trên nhóm lại các descriptor quan trọng để đọc, không phải toàn bộ stdout nguyên văn của `javap`.

Cặp `describe` có tên phương thức giống nhau nhưng kiểu tham số record khác nhau. Cặp `containerKind` khác ở `List` và `Set`. `summarizeNames` và `sumScores` dù đều nhận `List` vẫn khác **tên phương thức**.

Để kiểm tra ghi đè hợp lệ, lưu riêng hai lớp `GenericParent` và `CorrectChild` ở phần trước vào `CorrectOverrides.java`, biên dịch rồi chạy:

```shell
javac --release 17 -Xlint:all CorrectOverrides.java
javap -p -s -v CorrectChild
```

Ở class file của `CorrectChild`, tìm `save(String)` và phương thức `save(Object)` có cờ `ACC_BRIDGE, ACC_SYNTHETIC`. Đây là bằng chứng về phần triển khai do trình biên dịch sinh để phục vụ một override hợp lệ.

Không có class file mới hợp lệ cho chính một khai báo bị lỗi biên dịch. Khi thử các ví dụ lỗi, nên dùng thư mục riêng hoặc kiểm tra tránh nhầm với class file cũ còn sót từ lần biên dịch trước.

## 10. Những cách sửa không giải quyết đúng nguyên nhân

### Chuyển List<String> thành List<?> ở một overload

`List<?>` vẫn xóa về `List`. Nếu còn một overload cùng tên nhận `List<Integer>`, xung đột không biến mất.

### Dùng @SuppressWarnings

Name clash là lỗi khai báo, không phải một cảnh báo không được kiểm tra. Tắt cảnh báo không làm hai phương thức trở thành hợp lệ.

### Đổi kiểu trả về hoặc thêm throws

Không tạo khác biệt cần thiết cho chữ ký overload trong ngôn ngữ Java. Cần sửa tên, dãy tham số có ý nghĩa hoặc cấu trúc API.

### Chuyển sang kiểu thô

Một tham số chỉ ghi `List` vẫn xóa về `List`, đồng thời mất an toàn kiểu ở mã nguồn. Đây không phải cách sửa phù hợp.

### Kiểm tra kiểu phần tử đầu tiên để đoán List<String>

Danh sách có thể rỗng, có `null` hoặc có nội dung không đủ chứng minh hợp đồng của toàn bộ cấu trúc. Thông tin runtime của một phần tử không thay thế được việc thiết kế API có kiểu rõ ràng.

### Đổi List thành ArrayList chỉ để tạo overload

Kiểu sau xóa có thể khác, nhưng API bị ràng buộc vào một cách cài đặt cụ thể. Chỉ làm vậy khi phương thức thật sự yêu cầu khả năng riêng của kiểu đó; nếu không, đổi tên hoặc dùng một khai báo chung thường rõ ràng hơn.

## 11. Quy trình chẩn đoán và bài tập

Khi gặp name clash:

1. Ghi lại tất cả phương thức cùng tên, gồm cả phương thức từ lớp cha và interface có liên quan.
2. Viết kiểu sau xóa cho từng tham số; với biến kiểu, tìm giới hạn trái nhất.
3. So sánh dãy tham số, không dựa vào tên biến, kiểu trả về hoặc `throws`.
4. Nếu có kế thừa, kiểm tra chữ ký sau khi thay tham số kiểu của lớp cha theo lớp con và xem quan hệ override có hợp lệ không.
5. Chọn cách sửa theo mục đích API: tên riêng, một thuật toán generic, hoặc kiểu yêu cầu có ý nghĩa.
6. Biên dịch lại cả khai báo và các lời gọi tiêu biểu, gồm trường hợp có thể mơ hồ.

### Bài 1: List<String> và List<Long>

Có thể khai báo hai overload `load(List<String>)` và `load(List<Long>)` trong cùng lớp không?

**Đáp án:** không. Cả hai có dạng `load(List)` sau xóa.

### Bài 2: List<String> và Set<String>

Có thể khai báo `load(List<String>)` và `load(Set<String>)` không?

**Đáp án:** có thể về mặt xóa kiểu vì `List` khác `Set`. Vẫn cần xem thiết kế có lý do phân biệt hai loại chứa và các lời gọi có mơ hồ hay không.

### Bài 3: Number và tham số kiểu bị giới hạn

Cặp `<T extends Number> void put(T)` và `void put(Number)` có hợp lệ không?

**Đáp án:** không trong cùng lớp như hai khai báo riêng. Tham số `T` bị xóa thành `Number`.

### Bài 4: Đổi void thành String

Đổi kiểu trả về của một overload `process(List<Integer>)` từ `void` sang `String` có cứu được xung đột với `process(List<String>)` không?

**Đáp án:** không. Kiểu trả về không phân biệt overload theo cách đó trong Java.

### Bài 5: Lớp con của Parent<String>

Nên ghi đè bằng `save(String)` hay `save(Object)`?

**Đáp án:** `save(String)` theo hợp đồng lớp cha đã được tham số hóa, kèm `@Override` để kiểm tra. Trình biên dịch xử lý cầu nối cần thiết; không tự viết một phương thức `save(Object)` để bắt chước kiểu đã xóa.

Khả năng đọc hai lớp thông tin cùng lúc là trọng tâm của bài: generic giữ hợp đồng kiểu ở mã nguồn, còn erasure ảnh hưởng tới biểu diễn và các giới hạn của khai báo phương thức. Một API rõ ràng phải đúng ở cả hai lớp.
