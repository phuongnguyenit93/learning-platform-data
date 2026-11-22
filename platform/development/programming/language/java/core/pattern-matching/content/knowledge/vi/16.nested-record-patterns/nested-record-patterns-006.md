# Xử lý null ở từng cấp lồng trong nested record patterns (Java 21+)

Khi dùng **nested record patterns**, Java kiểm tra một record rồi tiếp tục khớp từng thành phần có thể là record khác. Nếu một mắt xích là `null`, kết quả phụ thuộc vào **pattern đang được áp dụng tại chính mắt xích đó**: record pattern không nhận `null`, còn một số component type patterns (đặc biệt `var`) có thể nhận `null`. Đây là điểm quyết định việc phân nhánh và tránh lỗi khi xử lý dữ liệu lồng nhau.

Bài sử dụng **Java 21 trở lên**. Record patterns được chuẩn hóa trong Java 21 (JEP 440), và pattern matching cho `switch` cũng được chuẩn hóa trong phiên bản này (JEP 441); không cần `--enable-preview`.

## 1. Cấu trúc record có nhiều cấp

Xét ba record lồng nhau và một thành phần dữ liệu cuối cùng:

```java
record Leaf(Object content) {}
record Branch(Leaf leaf) {}
record Tree(Branch branch) {}
```

Đường đi từ ngoài vào trong là:

```text
Tree
  └─ branch: Branch
       └─ leaf: Leaf
            └─ content: Object
```

Mặc định, record **không tự cấm `null` ở thành phần kiểu tham chiếu**. Vì thế tất cả các đối tượng sau đều hợp lệ về mặt cú pháp Java nếu không có kiểm tra riêng trong constructor:

```java
Tree a = null;
Tree b = new Tree(null);
Tree c = new Tree(new Branch(null));
Tree d = new Tree(new Branch(new Leaf(null)));
Tree e = new Tree(new Branch(new Leaf("OK")));
```

Năm trường hợp trên đặt `null` ở **năm tình huống khác nhau**: giá trị ngoài cùng, thành phần `branch`, thành phần `leaf`, thành phần `content` và không có giá trị `null`. Không nên gộp chúng thành một trường hợp chung.

## 2. Quy tắc cốt lõi: record pattern không khớp null

Xét biểu thức:

```java
input instanceof Tree(Branch(Leaf(var content)))
```

Java thực hiện việc khớp theo từng tầng:

1. `Tree(...)` kiểm tra `input` là một đối tượng `Tree` **khác `null`**.
2. `Branch(...)` kiểm tra giá trị của `Tree.branch()` là một đối tượng `Branch` **khác `null`**.
3. `Leaf(...)` kiểm tra giá trị của `Branch.leaf()` là một đối tượng `Leaf` **khác `null`**.
4. `var content` nhận giá trị của `Leaf.content()`. Vì đây là component type pattern không điều kiện đối với kiểu khai báo `Object`, **nó khớp cả khi `content` bằng `null`**.

Khi một record pattern ở bước 1, 2 hoặc 3 gặp `null`, toàn bộ nested record pattern không khớp. Với `instanceof`, kết quả là `false` và không có biến pattern nào của phép khớp đó được sử dụng trong nhánh thành công. Việc khớp thất bại do `null` **không tự gây `NullPointerException`**: Java không tiếp tục tách một record `null`.

Đáng chú ý: `var` ở bước 4 là pattern của **thành phần bên trong record**, không phải record pattern. Vì thế kết luận “bất kỳ `null` nào trong dữ liệu thì cả nested record pattern đều thất bại” là **sai**.

### Bảng kết quả theo vị trí null

| Giá trị của `input` | Cấp nào chứa `null` | `input instanceof Tree(Branch(Leaf(var content)))` | Lý do |
| --- | --- | --- | --- |
| `null` | Đối tượng ngoài | `false` | `Tree(...)` không khớp `null` |
| `new Tree(null)` | `branch` | `false` | `Branch(...)` không khớp `null` |
| `new Tree(new Branch(null))` | `leaf` | `false` | `Leaf(...)` không khớp `null` |
| `new Tree(new Branch(new Leaf(null)))` | `content` | `true` | `var content` nhận giá trị `null` |
| `new Tree(new Branch(new Leaf("OK")))` | Không có `null` | `true` | Cả ba record pattern khớp và `content` là `"OK"` |

Nếu thành phần `content` chứa `null`, trong nhánh khớp có thể kiểm tra ngay `content == null`, bởi biến này được khởi tạo hợp lệ dù giá trị của nó là `null`.

## 3. Giữ thành phần bằng var để tự xử lý null

Muốn nhận ra record cha **mà không bắt buộc record con khác `null`**, hãy dùng `var` thay cho record pattern lồng tại đúng cấp cần kiểm tra.

```java
Object input = new Tree(null);

if (input instanceof Tree(var branch)) {
    System.out.println(branch == null); // true
}
```

`Tree(var branch)` yêu cầu `input` là một `Tree` khác `null`, nhưng **không** yêu cầu `branch` khác `null`. Biến `branch` có kiểu suy ra là `Branch`, và giá trị của nó có thể là `null`.

Một cấp sâu hơn:

```java
Object input = new Tree(new Branch(null));

if (input instanceof Tree(Branch(var leaf))) {
    System.out.println(leaf == null); // true
}
```

Ở đây `Tree(...)` và `Branch(...)` đều phải nhận đối tượng record khác `null`; `var leaf` nhận thành phần `leaf` kể cả khi nó bằng `null`. Đổi thành `Tree(Branch(Leaf(var content)))` thì điều kiện **không** khớp, vì lúc đó Java phải áp dụng record pattern `Leaf(...)` lên `null`.

Quy tắc thực hành: **dừng tách tại cấp có thể `null` bằng `var`, kiểm tra giá trị, rồi chỉ tiếp tục truy cập khi hợp lệ**.

## 4. Không nhầm var với mọi type pattern

Sự khác nhau này còn áp dụng cho component type patterns. Với:

```java
record Box(Object content) {}
Object obj = new Box(null);
```

Các phép kiểm tra sau có kết quả:

```java
obj instanceof Box(var value)     // true; value == null
obj instanceof Box(Object value)  // true; value == null
obj instanceof Box(String value)  // false
```

Vì `Box` khai báo thành phần là `Object`:

- `var value` suy ra kiểu `Object` nên khớp kể cả `null`.
- `Object value` là type pattern không điều kiện so với kiểu thành phần `Object`; khi nằm bên trong record pattern, nó cũng khớp `null`.
- `String value` yêu cầu một giá trị `String` thực sự; thành phần `null` không khớp. Nó cũng không khớp nếu thành phần là đối tượng thuộc kiểu khác `String`.

Điều kiện chính xác là: **một type pattern xuất hiện trực tiếp trong danh sách thành phần của record pattern có thể khớp `null` nếu pattern đó không điều kiện (unconditional) đối với kiểu khai báo của thành phần**. `var` tại vị trí này là trường hợp thường gặp. Đây là quy tắc dành cho *component pattern*; `null instanceof Tree t` ở cấp ngoài vẫn là `false`.

Với thành phần kiểu nguyên thủy, chẳng hạn `record Counter(int count) {}`, `count` không thể có giá trị `null`. Vấn đề `null` chỉ phát sinh với kiểu tham chiếu (bao gồm kiểu bao `Integer`).

## 5. Phân loại null theo từng cấp bằng switch

Từ Java 21, có thể dùng `switch` với record patterns và `when` để diễn đạt rõ các nhánh:

```java
static String classify(Object input) {
    return switch (input) {
        case null -> "outer=null";
        case Tree(Branch(Leaf(var content))) ->
                content == null ? "content=null" : "complete";
        case Tree(Branch(var leaf)) when leaf == null ->
                "leaf=null";
        case Tree(var branch) when branch == null ->
                "branch=null";
        default -> "other";
    };
}
```

Cách đọc các nhánh:

1. `case null` nhận **giá trị đầu vào của `switch`** bằng `null`; nó không tự nhận `null` trong các record con.
2. `case Tree(Branch(Leaf(var content)))` áp dụng khi cả ba đối tượng record khác `null`. Nhánh này xử lý riêng `content == null`.
3. `case Tree(Branch(var leaf)) when leaf == null` dành cho `Tree` và `Branch` khác `null`, nhưng `leaf` là `null`.
4. `case Tree(var branch) when branch == null` dành cho `Tree` khác `null` nhưng `branch` là `null`.
5. `default` xử lý các đối tượng không thuộc những trường hợp trên (ví dụ `String`).

**Thứ tự nhánh có ý nghĩa:** kiểm tra cấu trúc cụ thể nhất trước, rồi lần lượt các trường hợp tách ít sâu hơn. Một pattern hoặc điều kiện rộng đặt quá sớm có thể che mất trường hợp cụ thể hoặc khiến các `case` phía sau bị trình biên dịch báo lỗi do *dominance*. Trong Java 21, khi cần bắt `null` bên trong record, dùng cách bắt thành phần bằng `var` rồi kiểm tra `when ... == null` như trên.

Đặc biệt, với `switch (input)`, nếu `input == null` và **không** có `case null` (hoặc nhánh xử lý `null` tương đương theo quy tắc ngôn ngữ), Java 21 có thể ném `NullPointerException` trước khi vào `default`. `default` không phải biện pháp thay thế cho `case null`.

## 6. Phương án if: kiểm tra tuần tự trước khi truy cập

Không bắt buộc phải sử dụng `switch`. Phương pháp đơn giản, dễ đặt breakpoint là kiểm tra từ ngoài vào trong:

```java
static String classifyWithIf(Object input) {
    if (input == null) {
        return "outer=null";
    }
    if (!(input instanceof Tree(var branch))) {
        return "other";
    }
    if (branch == null) {
        return "branch=null";
    }
    Leaf leaf = branch.leaf(); // an toàn: đã kiểm tra branch != null
    if (leaf == null) {
        return "leaf=null";
    }
    Object content = leaf.content(); // an toàn: đã kiểm tra leaf != null
    return content == null ? "content=null" : "complete";
}
```

Đoạn trên là **phương thức đặt bên trong lớp ở ví dụ dưới**, nơi `Tree`, `Branch`, `Leaf` đã được định nghĩa; bản thân đoạn phương thức không phải tệp Java độc lập. Ưu điểm là từng cấp `null` có nhánh riêng, tránh gọi `branch.leaf()` hoặc `leaf.content()` trước khi kiểm tra đối tượng nhận lời gọi. Trái lại, biểu thức `new Tree(null).branch().leaf()` sẽ gây `NullPointerException` do gọi `leaf()` trên `branch == null`.

## 7. Chương trình Java hoàn chỉnh và kết quả chạy

Lưu đoạn mã vào tệp **`NestedNullPatterns.java`**:

```java
public class NestedNullPatterns {
    record Leaf(Object content) {}
    record Branch(Leaf leaf) {}
    record Tree(Branch branch) {}
    record Box(Object content) {}

    static String classify(Object input) {
        return switch (input) {
            case null -> "outer=null";
            case Tree(Branch(Leaf(var content))) ->
                    content == null ? "content=null" : "complete";
            case Tree(Branch(var leaf)) when leaf == null ->
                    "leaf=null";
            case Tree(var branch) when branch == null ->
                    "branch=null";
            default -> "other";
        };
    }

    static void demo(Object value) {
        System.out.println(classify(value));
        System.out.println(
                "nested=" + (value instanceof Tree(Branch(Leaf(var content)))));
    }

    public static void main(String[] args) {
        demo(null);
        demo(new Tree(null));
        demo(new Tree(new Branch(null)));
        demo(new Tree(new Branch(new Leaf(null))));
        demo(new Tree(new Branch(new Leaf("OK"))));

        Object box = new Box(null);
        System.out.println("box-var=" + (box instanceof Box(var v)));
        System.out.println("box-Object=" + (box instanceof Box(Object v)));
        System.out.println("box-String=" + (box instanceof Box(String v)));
    }
}
```

Biên dịch và chạy bằng **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 -encoding UTF-8 NestedNullPatterns.java
java NestedNullPatterns
```

Kết quả:

```text
outer=null
nested=false
branch=null
nested=false
leaf=null
nested=false
content=null
nested=true
complete
nested=true
box-var=true
box-Object=true
box-String=false
```

Kết quả `nested=false` ở ba trường hợp đầu phản ánh lần lượt record ngoài, `Branch`, hoặc `Leaf` không thể khớp vì `null`. Khi chỉ `content` bằng `null`, kết quả chuyển thành `nested=true`: `var content` khớp và giữ nguyên `null`. Ba dòng cuối cho thấy `var` và `Object` chấp nhận `null` ở component `Box(Object)`, còn `String` không chấp nhận.

## 8. Chủ động đặt quy tắc không null trong record

Nếu nghiệp vụ yêu cầu `branch` luôn tồn tại, có thể ràng buộc dữ liệu ngay khi tạo record:

```java
record StrictTree(Branch branch) {
    StrictTree {
        java.util.Objects.requireNonNull(branch, "branch");
    }
}
```

Constructor dạng compact này từ chối `new StrictTree(null)` bằng `NullPointerException`. Có thể đặt kiểm tra tương tự ở `Branch.leaf` hoặc `Leaf.content` nếu từng thành phần phải khác `null` theo nghiệp vụ. Đây là **biện pháp đảm bảo bất biến dữ liệu**, không thay đổi nguyên tắc khớp `null` của record patterns. Các record `Tree`, `Branch`, `Leaf` trong ví dụ chạy ở trên cố ý cho phép `null` để quan sát rõ từng cấp.

Đừng mặc định mọi record được tạo bằng constructor mặc định đều đã có kiểm tra `null`: record tự động sinh accessor và constructor, nhưng việc cấm thành phần tham chiếu bằng `null` phải do người viết xác lập.

## 9. Lỗi thường gặp và cách tránh

1. **Nghĩ rằng `var` không nhận `null`.** Khi `var` là component pattern trong record pattern, nó có thể nhận `null`. Hãy kiểm tra biến đó trước khi gọi phương thức.
2. **Nghĩ rằng pattern lồng sâu an toàn nghĩa là dữ liệu chắc chắn đầy đủ.** `Tree(Branch(Leaf(var content)))` chỉ đảm bảo ba record ở đường đi khác `null`; `content` vẫn có thể là `null`.
3. **Dùng `case null` để xử lý mọi cấp lồng.** `case null` chỉ áp dụng cho đối tượng selector của `switch`. Đối với thành phần record, cần pattern phù hợp và điều kiện `when` hoặc `if`.
4. **Gọi accessor trước khi kiểm tra.** `tree.branch().leaf().content()` có thể ném `NullPointerException` khi thành phần trung gian là `null`. Hãy dùng nested record pattern hoặc kiểm tra tuần tự.
5. **Cho rằng type pattern nào cũng nhận `null`.** Khả năng nhận `null` của component type pattern phụ thuộc việc nó có *unconditional* đối với kiểu thành phần hay không; `Box(String s)` với `Box(Object)` và nội dung `null` là ví dụ không khớp.
6. **Đổi thứ tự các `case` một cách tùy tiện.** Các nhánh quá rộng có thể che các nhánh sâu. Hãy xử lý các hình dạng cụ thể rồi mới đến fallback, và biên dịch để kiểm tra dominance.
7. **Giả định `default` của switch xử lý selector `null`.** Với `switch` Java 21, nên nêu rõ `case null` khi selector có thể `null`.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Với `Object t = new Tree(new Branch(new Leaf(null)));`, biểu thức `t instanceof Tree(Branch(Leaf(var c)))` đúng hay sai? — **Đúng**; `c == null` bên trong nhánh khớp.

**Câu 2.** Với `Object t = new Tree(new Branch(null));`, biểu thức `t instanceof Tree(Branch(Leaf(var c)))` đúng hay sai? — **Sai**; `Leaf(...)` không khớp `null`. Muốn bắt thành phần này, có thể dùng `Tree(Branch(var leaf))` rồi kiểm tra `leaf == null`.

**Câu 3.** `Box(Object)` chứa `null` có khớp `Box(Object v)` không? — **Có**. Khi là component pattern và không điều kiện đối với kiểu thành phần `Object`, `Object v` nhận cả `null`.

**Câu 4.** Vì sao `switch` có `default` vẫn cần `case null`? — Vì `null` ở **selector** có cơ chế xử lý riêng; `default` không mặc nhiên nhận selector `null`.

**Tài liệu chính thức:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440](https://openjdk.org/jeps/440), [JEP 441](https://openjdk.org/jeps/441), [Java Language Specification 21, `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
