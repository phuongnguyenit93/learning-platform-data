# Mốc phiên bản của record patterns trong Java: từ preview đến tính năng chính thức

## 1. Mục tiêu: biết chính xác Java nào hỗ trợ record patterns

Khi đọc ví dụ Java có cú pháp như `obj instanceof Point(var x, var y)` hoặc `case Order(Customer(var name), var quantity) -> ...`, câu hỏi đầu tiên khi build thất bại là **project đang dùng phiên bản ngôn ngữ nào?** Có record trong chương trình **không đồng nghĩa** có thể dùng **record pattern** để phân rã record.

**Mốc cần ghi nhớ:** record patterns lần đầu xuất hiện dưới dạng **preview ở Java 19** (JEP 405), được **preview lần hai ở Java 20** (JEP 432), rồi trở thành **tính năng chính thức ở Java 21** (JEP 440). Từ Java 21, mã record pattern chuẩn không cần `--enable-preview`.

Bài học thuộc nhóm **Tương thích Java**, tập trung vào:

- Phân biệt **record class** với **record pattern** và pattern matching cho `instanceof`/`switch`.
- Nắm dòng thời gian Java 14–22, trạng thái preview/chính thức và mã JEP tương ứng.
- Hiểu lý do **Java 17 có record nhưng không có record patterns**, và cách viết phương án thay thế.
- Biết sử dụng `javac --release` và các cờ preview trong môi trường phù hợp.
- Hiểu một vài thay đổi cú pháp từ hai vòng preview đến Java 21, không sao chép cú pháp cũ một cách máy móc.
- Kiểm tra một chương trình Java 21 hoàn chỉnh dùng record pattern lồng, `instanceof`, `switch`, `when` và generic inference.
- Phân biệt record patterns của Java 21 với **unnamed pattern `_`** chính thức từ Java 22.

Một sai lầm phổ biến là nói “record patterns có từ Java 16” chỉ vì **record** chính thức từ Java 16. Điều đó không đúng: **khai báo record** và **phân rã record bằng pattern** là hai bước phát triển khác nhau của Java.

## 2. Ba tính năng liên quan nhưng không trùng nhau

### 2.1. Record class: kiểu dữ liệu, chính thức từ Java 16

Record khai báo dữ liệu bất biến ở mức các component (các trường thành phần là `private final`; record có thể chứa tham chiếu tới đối tượng bên trong vẫn mutable). Ví dụ:

```java
record Point(int x, int y) {}

Point p = new Point(2, 3);
System.out.println(p.x()); // 2
System.out.println(p.y()); // 3
```

Record tự cung cấp các accessor `x()`, `y()`, constructor canonical, `equals`/`hashCode`/`toString` theo quy tắc của record. Ngôn ngữ hỗ trợ record theo lộ trình:

- **Java 14:** Record Classes lần đầu preview (JEP 359).
- **Java 15:** Record Classes second preview (JEP 384).
- **Java 16:** Records trở thành chính thức (JEP 395).
- **Java 17:** Dùng record bình thường như tính năng chuẩn, nhưng **chưa có record patterns**.

Vì thế chương trình trên có thể nằm trong project Java 17. Không cần record pattern để tạo object hoặc gọi accessor.

### 2.2. Type pattern: kiểm tra kiểu và ràng buộc biến, chính thức từ Java 16

Từ Java 16, `instanceof` hỗ trợ type pattern:

```java
static String summary(Object input) {
    if (input instanceof Point point) {
        return point.x() + "," + point.y();
    }
    return "not a point";
}
```

Ở đây `Point point` kiểm tra và ràng buộc **toàn bộ đối tượng** thành một biến kiểu `Point`. Ta vẫn gọi `point.x()`, `point.y()`; mã này chưa phải deconstruction bằng record pattern. Tính năng này chuẩn hóa qua **JEP 394** trong Java 16.

### 2.3. Record pattern: kiểm tra record và phân rã các component, chính thức từ Java 21

Với Java 21:

```java
static String summary21(Object input) {
    if (input instanceof Point(var x, var y)) {
        return x + "," + y;
    }
    return "not a point";
}
```

Pattern `Point(var x, var y)` kiểm tra đối tượng có khớp record `Point` không, rồi lấy từng component thành biến `x`, `y`. Không cần tạo biến toàn bộ `point` và gọi accessor một cách tường minh trong code sử dụng.

Hai phương thức `summary` và `summary21` ở trên có thể cho cùng kết quả, nhưng **yêu cầu phiên bản compiler khác nhau**. Đây là trọng tâm của tương thích nguồn (source compatibility).

## 3. Bảng mốc phiên bản quan trọng

| Phiên bản | Trạng thái record class | Trạng thái record patterns | JEP liên quan | Hệ quả cho project |
| --- | --- | --- | --- | --- |
| **Java 14** | Preview lần đầu | Chưa hỗ trợ | JEP 359 | Chưa viết được `Point(var x, var y)`. |
| **Java 15** | Preview lần hai | Chưa hỗ trợ | JEP 384 | Chưa có record deconstruction pattern. |
| **Java 16** | **Chính thức** | Chưa hỗ trợ | JEP 395; type pattern `instanceof` JEP 394 | Dùng `record` và `instanceof Point point`, truy cập bằng accessor. |
| **Java 17** | Chính thức | Chưa hỗ trợ | Record chuẩn; `switch` pattern JEP 406 preview riêng | Không thể dùng `Point(var x, var y)` như cú pháp record pattern. |
| **Java 18** | Chính thức | Chưa hỗ trợ | `switch` pattern JEP 420 second preview riêng | Cờ preview cho switch không tự tạo record patterns. |
| **Java 19** | Chính thức | **Preview lần đầu** | **JEP 405** | Muốn biên dịch/chạy record patterns cần bật preview trên JDK 19. |
| **Java 20** | Chính thức | **Preview lần hai** | **JEP 432** | Tiếp tục cần preview trên JDK 20; có thay đổi tính năng so với Java 19. |
| **Java 21** | Chính thức | **Chính thức (final)** | **JEP 440** | Dùng record patterns trực tiếp, không cần cờ preview. |
| **Java 22+** | Chính thức | Chính thức | JEP 440; unnamed patterns JEP 456 (Java 22) | Có thể thêm cú pháp `_` để bỏ qua component không sử dụng. |

Đừng đánh đồng `switch` pattern và record patterns: **pattern matching for `switch`** có lộ trình preview riêng từ **Java 17** (JEP 406), qua Java 18 (JEP 420), Java 19 (JEP 427), Java 20 (JEP 433), rồi chính thức **Java 21** (JEP 441). Trong khi đó **record patterns** chỉ bắt đầu preview từ **Java 19**.

**Mốc thực tiễn:** Nếu phát triển Java 17 LTS và cần codebase không dùng preview, sử dụng `record` với accessor hoặc type pattern. Nếu sử dụng Java 21 LTS, bạn có thể dùng record patterns ở cả `instanceof` và `switch` như tính năng ổn định.

## 4. Java 19 — JEP 405: lần preview đầu tiên

**JEP 405 — Record Patterns (Preview)** đưa vào khả năng deconstruct record dựa trên pattern. Ý tưởng là cho phép lập trình viên diễn đạt cấu trúc dữ liệu cần khớp một cách khai báo, thay vì viết liên tiếp nhiều phép `instanceof`, cast và accessor.

Ví dụ về ý tưởng (dùng cú pháp ổn định của Java 21 để giải thích cơ chế):

```java
record Point(int x, int y) {}

static int sum(Object raw) {
    if (raw instanceof Point(var x, var y)) {
        return x + y;
    }
    return 0;
}
```

Ở Java 19, record patterns còn **preview**, nên muốn dùng tính năng đó cần JDK 19 và bật preview cho **bản phát hành 19**. Chẳng hạn, với một chương trình đã được viết phù hợp cú pháp và API của Java 19:

```bash
# Chỉ khi thực sự dùng JDK 19 và mã nguồn preview hợp lệ với Java 19:
javac --enable-preview --release 19 RecordPatternPreviewDemo.java
java --enable-preview RecordPatternPreviewDemo
```

Tên tệp `RecordPatternPreviewDemo.java` trong cặp lệnh này là tên minh họa cho một chương trình riêng tương thích Java 19, **không phải tên tệp của chương trình chạy đầy đủ ở mục 8**. Không mặc định lấy nguyên một tệp Java 21 có guard, inference hoặc cú pháp mới rồi cho rằng nó chạy nguyên vẹn trên Java 19.

**Preview là gì?** Tính năng đã được triển khai để thử nghiệm và lấy phản hồi nhưng chưa có cam kết ổn định như một tính năng chính thức. Cú pháp và quy tắc có thể thay đổi giữa các bản preview và bản final. Bởi vậy, trong dự án yêu cầu tương thích lâu dài, code preview nên được đánh dấu rõ giới hạn version và được kiểm thử trên đúng JDK.

## 5. Java 20 — JEP 432: second preview và một số thay đổi

**JEP 432 — Record Patterns (Second Preview)** đưa record patterns trở lại Java 20 với các cải tiến sau phản hồi từ Java 19. Hai điểm đáng biết khi đọc mã lịch sử:

1. **Suy luận type arguments cho generic record patterns** được mở rộng, giảm nhu cầu ghi tường minh một số tham số kiểu trong ngữ cảnh mà compiler đã biết. Đây là một bước tiến quan trọng đối với nested/generic record deconstruction.
2. **Named record patterns** từng được hỗ trợ trong Java 19 preview không còn được hỗ trợ ở Java 20 preview. Vì vậy, đừng sao chép cú pháp preview cũ từ tài liệu Java 19 sang code Java 20/21 mà không kiểm tra.

Ngoài ra, ở **Java 20 preview**, record patterns có thể xuất hiện trong phần khai báo biến lặp của **enhanced `for`**. Khả năng này **không còn trong bản record patterns final của Java 21**. Điều đó nghĩa là mã preview từng hợp lệ trong vòng lặp có thể cần refactor khi nâng lên Java 21; hãy giữ `for (var element : list)` rồi dùng `instanceof Record(...)` trong thân vòng lặp khi phù hợp.

Java 20 vẫn cần bật preview khi sử dụng record pattern:

```bash
# Chỉ dùng JDK 20; mã ví dụ riêng phải hợp lệ với Java 20 preview:
javac --enable-preview --release 20 RecordPatternPreviewDemo.java
java --enable-preview RecordPatternPreviewDemo
```

Cần **khớp phiên bản JDK và release preview**. Một JDK hiện đại không thể tùy ý bật preview tính năng cũ bằng `--enable-preview --release 19`/`20` để giả lập chính xác môi trường cũ: preview chỉ bật cho bản phát hành được compiler hiện tại hỗ trợ. Muốn kiểm thử mã Java 19/20 preview thật sự, dùng đúng toolchain Java 19/20 tương ứng.

**Cảnh báo tương thích:** Khi migrate Java 19 → 20 → 21, hãy đọc cảnh báo compiler về preview, cú pháp bị bỏ, cách suy luận kiểu và bối cảnh được phép đặt record pattern. Mục tiêu không chỉ thay đổi số release mà còn cập nhật nguồn code nếu ngôn ngữ thay đổi.

## 6. Java 21 — JEP 440: record patterns trở thành tính năng chính thức

Từ **Java 21**, record patterns đã được chuẩn hóa (JEP 440). Các kịch bản tiêu biểu gồm:

- **`instanceof` với record pattern:** `input instanceof Point(var x, var y)`.
- **Nested record patterns:** `input instanceof ColoredPoint(Point(var x, var y), var color)`.
- **`switch` với record pattern:** `case Point(var x, var y) -> ...` khi selector có kiểu phù hợp.
- **`when` guard trong `switch`:** `case Point(var x, var y) when x == y -> ...` (cần pattern matching cho switch chính thức từ JEP 441, cũng ở Java 21).
- **Generic record patterns:** trình biên dịch có thể suy luận type arguments trong những trường hợp thích hợp.

Java 21 không yêu cầu `--enable-preview` để dùng các cú pháp chuẩn trên. Ví dụ một dự án đặt release level 21:

```bash
javac --release 21 RecordPatternVersionDemo.java
java RecordPatternVersionDemo
```

Lệnh chạy trong đoạn trên dành cho **tệp đầy đủ ở mục 8**. `--release 21` yêu cầu compiler JDK có hỗ trợ target Java 21; nó không phải cờ bật preview. Project build bằng JDK 17 không thể biên dịch nguồn Java 21 bằng cách thêm `--release 21` vì compiler JDK 17 không hỗ trợ target ấy.

**Lưu ý quan trọng:** Mã nguồn có `record` thôi chưa làm nó trở thành mã record pattern. Ví dụ `record Point(int x, int y)`, `new Point(1, 2)` và `point.x()` đã hoạt động trên Java 16/17. Chỉ những chỗ kiểm tra và phân rã bằng cú pháp `Point(...)` trong pattern mới yêu cầu record patterns.

## 7. Java 21 và Java 22: đừng nhầm record pattern với unnamed pattern _

Với Java 21 **không bật preview**, khi một component không được sử dụng, có thể vẫn phải ghi đủ vị trí và đặt tên biến:

```java
record Point(int x, int y) {}

// Java 21 ổn định: đủ hai component, dù không dùng y.
static int xOnly(Object value) {
    if (value instanceof Point(var x, var ignoredY)) {
        return x;
    }
    return -1;
}
```

Cú pháp **unnamed pattern `_`** có lộ trình riêng:

- **Java 21:** *Unnamed Patterns and Variables* ở trạng thái **preview**, qua **JEP 443**; không phải tính năng chuẩn mặc định của Java 21.
- **Java 22:** *Unnamed Variables & Patterns* trở thành **chính thức**, qua **JEP 456**.

Với Java 22+ có thể viết:

```java
// Java 22+, không phải cú pháp chuẩn của Java 21 mặc định.
record Point(int x, int y) {}

static int xOnly(Object input) {
    return switch (input) {
        case Point(var x, _) -> x;
        default -> -1;
    };
}
```

Nếu dùng mã Java 21 không bật preview, hãy chọn `var ignoredY` thay vì `_` để bảo đảm tương thích. **Dấu gạch dưới không làm component biến mất khỏi danh sách pattern**: record pattern vẫn phải khớp đúng số lượng và thứ tự component.

Một dự án có thể dùng JDK 22 hoặc JDK mới hơn nhưng đặt `--release 21` để phát hành mã cho Java 21; khi đó các tính năng chuẩn chỉ từ Java 22 (như unnamed patterns `_`) **không hợp lệ** ở source level 21. Phiên bản JDK đang cài và source level đang biên dịch là hai yếu tố khác nhau.

## 8. Ví dụ hoàn chỉnh Java 21: records, instanceof, switch, nested và generic

Tạo tệp **`RecordPatternVersionDemo.java`**:

```java
public class RecordPatternVersionDemo {
    record Point(int x, int y) {}
    record ColoredPoint(Point point, String color) {}
    record Pair<T>(T first, T second) {}

    static String legacy(Object input) {
        if (!(input instanceof ColoredPoint value)) return "not-colored-point";
        if (value.point() == null) return "missing-point";
        return value.color() + ":" + value.point().x() + "," + value.point().y();
    }

    static String withInstanceof(Object input) {
        if (input instanceof ColoredPoint(Point(var x, var y), var color)) {
            return color + ":" + x + "," + y;
        }
        if (input instanceof ColoredPoint(var point, var color)) return "missing-point";
        return "not-colored-point";
    }

    static String withSwitch(Object input) {
        return switch (input) {
            case null -> "null-input";
            case ColoredPoint(Point(var x, var y), var color) when x == y ->
                    "diagonal:" + color + ":" + x;
            case ColoredPoint(Point(var x, var y), var color) ->
                    "point:" + color + ":" + x + "," + y;
            case ColoredPoint(var point, var color) -> "missing-point";
            case Point(var x, var y) -> "bare-point:" + x + "," + y;
            default -> "other";
        };
    }

    static String generic(Pair<String> pair) {
        if (pair instanceof Pair(var first, var second)) {
            return first + "|" + second;
        }
        return "null-pair";
    }

    public static void main(String[] args) {
        Object normal = new ColoredPoint(new Point(2, 3), "red");
        Object diagonal = new ColoredPoint(new Point(4, 4), "blue");
        Object absent = new ColoredPoint(null, "none");

        System.out.println("record=" + normal.getClass().getSimpleName());
        System.out.println("legacy=" + legacy(normal));
        System.out.println("instanceof=" + withInstanceof(normal));
        System.out.println("switch=" + withSwitch(normal));
        System.out.println("diagonal=" + withSwitch(diagonal));
        System.out.println("missing.legacy=" + legacy(absent));
        System.out.println("missing.instanceof=" + withInstanceof(absent));
        System.out.println("missing.switch=" + withSwitch(absent));
        System.out.println("bare=" + withSwitch(new Point(8, 9)));
        System.out.println("null=" + withSwitch(null));
        System.out.println("other=" + withSwitch("java"));
        System.out.println("generic=" + generic(new Pair<>("A", "B")));
        System.out.println("generic.null=" + generic(null));
        System.out.println("equal=" + legacy(normal).equals(withInstanceof(normal)));
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 RecordPatternVersionDemo.java
java RecordPatternVersionDemo
```

**Stdout đúng:**

```text
record=ColoredPoint
legacy=red:2,3
instanceof=red:2,3
switch=point:red:2,3
diagonal=diagonal:blue:4
missing.legacy=missing-point
missing.instanceof=missing-point
missing.switch=missing-point
bare=bare-point:8,9
null=null-input
other=other
generic=A|B
generic.null=null-pair
equal=true
```

**Điểm cần đọc kỹ:**

1. **`legacy`** dùng type pattern `instanceof ColoredPoint value` (chuẩn từ Java 16), sau đó gọi các accessor. Đây là cách triển khai thân thiện với Java 17.
2. **`withInstanceof`** dùng nested record pattern `ColoredPoint(Point(var x, var y), var color)`, yêu cầu **Java 21** để dùng như tính năng chuẩn. Khi `point == null`, nested `Point(...)` không khớp; nhánh `ColoredPoint(var point, var color)` tiếp theo bắt trường hợp ấy.
3. **`withSwitch`** dùng record patterns trong `case` và `when x == y`. Khi `Point(4,4)` khớp điều kiện đường chéo, nhánh đầu trả `diagonal:blue:4`; với `Point(2,3)`, guard sai nên nhánh record không guard phía sau trả `point:red:2,3`.
4. **`generic`** nhận `Pair<String>`. Pattern `Pair(var first, var second)` suy luận kiểu các component theo ngữ cảnh. Nếu `pair == null`, `instanceof` trả false và kết quả là `null-pair`.
5. **`case null`** bắt selector null trong `switch`. Với một `switch` pattern thiếu xử lý null, `default` không tự bảo đảm thay cho chính sách xử lý null và có thể phát sinh `NullPointerException`.
6. **`equal=true`** xác nhận hai phương thức `legacy` và `withInstanceof` cho cùng kết quả với input bình thường đã thử; đó không tự động chứng minh chúng tương đương cho mọi dữ liệu.

Chương trình chỉ dùng tính năng **ổn định ở Java 21**, không sử dụng unnamed pattern `_` hay cú pháp preview đã bị loại bỏ trong Java 20/21.

## 9. Khi build bằng Java 17: mã record class hợp lệ, deconstruction pattern không hợp lệ

Java 17 hỗ trợ record class và type pattern `instanceof`, nên có thể thay record pattern bằng accessor rõ ràng:

```java
// Record + type pattern: chạy trên Java 17.
public class CompatibleWith17 {
    record Point(int x, int y) {}

    static String show(Object input) {
        if (input instanceof Point point) {
            return point.x() + "," + point.y();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(show(new Point(2, 3)));
        System.out.println(show(null));
    }
}
```

Lệnh:

```bash
javac --release 17 CompatibleWith17.java
java CompatibleWith17
```

Kết quả:

```text
2,3
other
```

Nếu ở cùng chế độ Java 17 lại viết:

```java
// KHÔNG BIÊN DỊCH với source/release 17:
if (input instanceof Point(var x, var y)) {
    return x + "," + y;
}
```

Compiler từ chối cú pháp deconstruction, vì record patterns **chưa có ở Java 17**, không phải vì record `Point` không hợp lệ. Với compiler mới hỗ trợ `--release 17`, thông báo có thể tương tự **“deconstruction patterns are not supported in -source 17”**.

**Không sửa bằng cách thêm `--enable-preview` vào lệnh Java 17.** Preview của Java 17 liên quan những tính năng đã được cung cấp trong bản Java 17; record patterns chỉ được giới thiệu sau đó, ở Java 19. Muốn dùng record patterns như tính năng chuẩn, nâng source/release lên **21** và sử dụng toolchain hỗ trợ Java 21.

## 10. Tác động của --release, --source, --enable-preview

Đối với Java:

- `java -version` cho biết JVM runtime đang sử dụng trong phiên terminal.
- `javac -version` cho biết phiên bản Java compiler được chọn qua `PATH`/toolchain.
- `javac --release N` yêu cầu compiler biên dịch nguồn theo ngôn ngữ/API/class file phù hợp phiên bản `N` mà compiler hỗ trợ. Một JDK mới có thể target Java cũ, nhưng **không thể dùng tính năng ngôn ngữ mới hơn target**.
- `--enable-preview` bật tính năng preview thuộc phiên bản tương ứng. Nó **không phải công tắc “bật mọi tính năng tương lai”**.

### Công thức kiểm tra theo phiên bản

| Mục tiêu | JDK cần có | Ví dụ cách biên dịch | Cách chạy |
| --- | --- | --- | --- |
| Java 17 record class + type pattern | JDK 17+ có target 17 | `javac --release 17 CompatibleWith17.java` | `java CompatibleWith17` trên runtime phù hợp |
| Java 19 record pattern preview | **JDK 19** | `javac --enable-preview --release 19 PreviewDemo19.java` | `java --enable-preview PreviewDemo19` trên JDK 19 |
| Java 20 record pattern second preview | **JDK 20** | `javac --enable-preview --release 20 PreviewDemo20.java` | `java --enable-preview PreviewDemo20` trên JDK 20 |
| Java 21 record pattern chính thức | JDK 21+ có target 21 | `javac --release 21 RecordPatternVersionDemo.java` | `java RecordPatternVersionDemo` trên JDK 21+ |

Tên `PreviewDemo19.java`, `PreviewDemo20.java` trong bảng là **ví dụ đặt tên cho dự án riêng** sử dụng cú pháp preview của từng phiên bản; không phải tệp đã cung cấp mã trong bài này. Chương trình đầy đủ, đã có mã và stdout kiểm chứng, là `RecordPatternVersionDemo.java` ở mục 8.

Dự án cũng phải kiểm tra **runtime phiên bản triển khai**. Ví dụ, biên dịch tệp với target Java 21 tạo class files phù hợp Java 21; việc sao chép class đó vào runtime Java 17 có thể gây `UnsupportedClassVersionError`, độc lập với việc cú pháp record pattern đúng hay sai.

Nếu đang dùng IDE hoặc CI, “JDK đã cài trên máy” chưa chắc trùng với JDK thực sự mà Maven, Gradle, IDE hay pipeline đang gọi. Vì vậy, khi gặp lỗi bất thường, kiểm tra **compiler thực tế và source/release level**, không chỉ runtime hiện ra trong một terminal khác.

## 11. Đặt Java 21 cho Maven/Gradle và xử lý lỗi tương thích

### Maven

Với project thực sự muốn dùng Java 21 chuẩn:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đây là phần cấu hình minh họa đặt trong `pom.xml`, với Maven Compiler Plugin/thiết lập build hỗ trợ thuộc tính trên. Đảm bảo Maven sử dụng JDK có khả năng target Java 21. Khi đó record patterns Java 21 biên dịch như tính năng chính thức, **không thêm cờ preview**.

Nếu cần giữ Java 17 compatibility, đặt `maven.compiler.release` bằng `17` và refactor các record patterns thành `instanceof Type variable`/accessor.

### Gradle Groovy DSL

Ví dụ toolchain Java 21:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đặt trong file `build.gradle` của một Java project thích hợp. Tùy build, bạn có thể cấu hình `options.release = 21` nếu cần ràng buộc rõ target. Đừng chỉ cài JDK 21 trong hệ điều hành rồi giả định Gradle/IDE sẽ tự đổi source level.

### Cách đọc lỗi compiler

- **“deconstruction patterns are not supported in -source 17”**: đang biên dịch mã record pattern bằng source level không hỗ trợ.
- **“invalid source release: 21”** (hoặc thông báo tương đương): compiler quá cũ để target Java 21; nâng JDK compiler/toolchain.
- **“preview features are disabled by default”** với code preview Java 19/20: cần bật preview trên đúng phiên bản.
- **“preview features ... only supported for release ...”**: compiler không chấp nhận cố bật preview cho target phiên bản cũ tùy ý; sử dụng toolchain đúng.
- **“cannot find symbol”** hoặc lỗi pattern inference: có thể do code lấy từ preview với cú pháp đã thay đổi, sai type arguments, thiếu component hoặc thiếu import; không nhất thiết chỉ do version.

Luôn đọc phần **source/release** trong log build và kiểm tra class/method thật sự đang gặp lỗi trước khi thay cấu hình diện rộng.

## 12. Các thay đổi preview dễ gây nhầm khi nâng version

### 12.1. Named record patterns của Java 19 preview

Bản preview đầu tiên có một số hình thức record pattern không được giữ nguyên sau đó. JEP 432 ở Java 20 loại **named record patterns**, trong khi Java 21 dùng hình thức record pattern ổn định:

```java
// Java 21: deconstruct các component, dùng biến tại scope của nhánh.
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Đoạn trên là snippet đặt trong nơi có `input` kiểu phù hợp, không phải một file độc lập. Nếu cần giữ biến trỏ tới **toàn bộ record**, dùng một type pattern riêng:

```java
if (input instanceof Point point) {
    System.out.println(point.x() + point.y());
}
```

Không tự ghép cú pháp named record pattern từ bài blog preview 19 vào project 21 rồi mong compiler hiểu. Khi migrate, hãy viết lại theo **record pattern** hoặc **type pattern** chuẩn.

### 12.2. Enhanced for có record pattern trong Java 20 preview, không có ở Java 21 final

JEP 432 đã thử cho phép record pattern trong phần header của vòng `for-each`. JEP 440 **loại hỗ trợ đó** khỏi cú pháp final. Cách viết Java 21 an toàn là:

```java
// Mẫu Java 21: dùng phần tử trong for-each rồi deconstruct bên trong.
for (Object element : values) {
    if (element instanceof Point(var x, var y)) {
        System.out.println(x + y);
    }
}
```

Đây là snippet cần biến `values` từ ngữ cảnh chương trình. Nó không tạo file standalone và không thể tự chạy nếu thiếu dữ liệu `values`. Ý chính là phân rã trong **thân vòng lặp**, thay vì phụ thuộc cú pháp preview Java 20 từng cho phép.

### 12.3. Generic record patterns

Mã generic như `record Pair<T>(T first, T second) {}` đòi hỏi compiler xác định kiểu component và quy tắc khớp. Lộ trình preview đã cải thiện khả năng suy luận type arguments, đặc biệt từ JEP 432. Trong Java 21, nếu ngữ cảnh đủ rõ, có thể viết `Pair(var first, var second)` như trong phương thức `generic` ở mục 8.

Nhưng generic type erasure vẫn tồn tại. Không nghĩ rằng một check từ `Object` như `instanceof List<String>` có thể chứng minh mọi phần tử đều là `String` tại runtime; nó không hợp lệ trong tình huống thông thường. Hãy dùng `List<?>` và kiểm tra các phần tử hoặc dùng schema phù hợp. Record pattern generic inference **không xóa bỏ** giới hạn runtime type erasure.

## 13. Quy trình nâng cấp từ Java 17/19/20 lên Java 21

Giả sử project chuẩn bị dùng record patterns nhưng còn phần build cũ:

1. **Xác định mục tiêu triển khai:** runtime production/CI có hỗ trợ Java 21 không? Có module hoặc thư viện bắt buộc chạy trên Java 17 không? Nếu có, phải giữ phần đó tương thích Java 17 hoặc tách code thích hợp.
2. **Đọc source level thật:** kiểm tra `javac -version`, `java -version`, `--release`, Maven/Gradle toolchain và IDE language level.
3. **Phân biệt record với record pattern:** record type có thể tiếp tục ở Java 17; chỉ code deconstruction pattern mới yêu cầu 21 nếu không muốn preview.
4. **Với code preview 19/20:** rà soát cú pháp named patterns, record pattern trong enhanced-for header, và generic type inference; đừng chỉ xóa `--enable-preview` rồi giữ nguyên mọi syntax.
5. **Nâng compiler/source level lên 21:** đặt JDK/toolchain và target release 21 thống nhất với dự án. Gỡ cờ preview nếu không dùng tính năng preview nào khác.
6. **Biên dịch toàn bộ tests:** đảm bảo các `case` với `when`, `null`, nested record patterns và exhaustiveness của `switch` hợp lệ.
7. **Chạy test trên Java 21 runtime:** kiểm tra cả đường match, non-match, record con null, component null, giá trị biên và ngoại lệ.
8. **Kiểm tra thư viện và pipeline:** framework, build plugins, static analyzers, code formatter, coverage tools và code generation cần hiểu cú pháp/bytecode Java 21.
9. **Không lẫn cú pháp Java 22:** nếu cần hỗ trợ Java 21, giữ `var ignored` thay cho unnamed pattern `_` dù máy develop có JDK mới.
10. **Cập nhật tài liệu version:** ghi rõ tối thiểu Java 21 cho module sử dụng record patterns, tránh người đọc chạy lệnh `javac --release 17` rồi hiểu sai lỗi.

**Lựa chọn bảo thủ:** Nếu code chỉ cần một hoặc hai component và vẫn phải chạy trên Java 17, dùng `instanceof Point point` rồi accessor. Record patterns là cú pháp giúp code khai báo cấu trúc rõ ràng hơn, không phải điều kiện bắt buộc để thao tác với dữ liệu record.

## 14. Bảng lỗi thường gặp về mốc phiên bản

| Nhận định hoặc lỗi | Thực tế | Cách khắc phục |
| --- | --- | --- |
| “Có record từ Java 16 nên record patterns cũng từ Java 16” | Java 16 chuẩn hóa **record** (JEP 395) và type pattern `instanceof` (JEP 394); record patterns chỉ bắt đầu preview Java 19. | Phân biệt ba tính năng; dùng accessor trên Java 17. |
| “Java 17 đã có pattern switch preview nên có record patterns” | Pattern matching for switch và record patterns có lịch phát triển riêng. | Muốn record patterns chuẩn, dùng Java 21+. |
| “Java 19 đã hỗ trợ ổn định record patterns” | Java 19 **preview** lần đầu (JEP 405). | Bật preview với JDK 19 nếu bắt buộc dùng code preview; cân nhắc nâng 21. |
| “Java 20 là bản final” | Java 20 là **second preview** (JEP 432). | Chờ/nâng Java 21 để dùng chuẩn. |
| “Java 21 vẫn bắt buộc --enable-preview cho record patterns” | Java 21 **final** (JEP 440). | Dùng `javac --release 21` bình thường. |
| “Java 21 có dấu _ làm unnamed pattern chuẩn” | Java 21 JEP 443 là **preview**; Java 22 JEP 456 mới final. | Dùng `var ignored` trên Java 21 không preview. |
| “Mã enhanced-for record pattern chạy Java 20 preview phải chạy Java 21” | Hỗ trợ trong header enhanced for đã **bị loại** ở Java 21. | Đưa `instanceof Record(...)` vào thân vòng lặp. |
| “Dùng JDK 24 nhưng --release 17 vẫn được dùng record patterns” | `--release 17` chọn ngôn ngữ/API Java 17. | Nâng release lên 21 hoặc bỏ record pattern. |
| “Chỉ cần --enable-preview --release 19 với bất kỳ JDK mới” | Preview chỉ áp dụng cho release mà compiler hỗ trợ ở thời điểm đó. | Dùng đúng JDK 19/20 cho mã preview lịch sử. |
| “Pair(var x, var y) kiểm tra generic runtime types hoàn hảo” | Compiler suy luận kiểu trong ngữ cảnh, nhưng erasure vẫn hạn chế kiểm tra runtime. | Kiểm tra hợp đồng dữ liệu; đừng biến generic inference thành phép xác nhận `List<String>`. |
| “Có --release 21 rồi thì chạy class trên JRE 17 được” | Class file và runtime phải tương thích; Java 17 không chạy class target 21. | Đảm bảo runtime production Java 21+ hoặc phát hành mã 17 tương thích. |
| “Không match nested record pattern nghĩa là mọi component khác null” | Nested record con null sẽ không khớp; component được ràng buộc bằng `var` vẫn có thể null. | Test null các tầng record và component riêng. |

## 15. Bài tập tự kiểm tra phiên bản và lựa chọn giải pháp

### Tình huống A: dự án bắt buộc Java 17

Bạn có:

```java
record User(String name, int age) {}

static String label(Object raw) {
    if (raw instanceof User(var name, var age)) {
        return name + ":" + age;
    }
    return "other";
}
```

**Câu hỏi:** Vì sao project Java 17 không biên dịch? Có bắt buộc bỏ `record User` không?

**Đáp án:** Không cần bỏ record. Java 17 đã hỗ trợ record class, nhưng chưa hỗ trợ record deconstruction pattern. Refactor thành type pattern + accessor:

```java
static String label(Object raw) {
    if (raw instanceof User user) {
        return user.name() + ":" + user.age();
    }
    return "other";
}
```

Hai phương thức là snippet đặt trong class có khai báo `record User`. Phiên bản thứ hai phù hợp Java 17.

### Tình huống B: dự án Java 20 preview chuyển lên 21

Source cũ dùng record patterns trong header enhanced `for`. Project team thay `--release 20` thành `--release 21` nhưng compiler báo lỗi.

**Đáp án:** Hãy kiểm tra lại cú pháp lịch sử: Java 20 preview từng hỗ trợ record pattern trong header enhanced-for nhưng bản final Java 21 đã loại. Dùng biến phần tử bình thường trong `for (var element : collection)` rồi deconstruct bằng `instanceof Record(...)` bên trong thân vòng lặp. Kiểm tra cả generic inference và các named record patterns từ preview cũ.

### Tình huống C: máy phát triển có JDK 22, production là Java 21

Một developer muốn viết `case Point(var x, _) -> ...` trong module đang target Java 21.

**Đáp án:** Không dùng cú pháp `_` chuẩn Java 22 khi biên dịch `--release 21`. Viết `case Point(var x, var ignoredY) -> ...` hoặc chọn type pattern và accessor. JDK đang chạy compiler mới hơn không đồng nghĩa source level mục tiêu tự động mới hơn.

### Tình huống D: câu hỏi trắc nghiệm nhanh

- Record class final ở Java nào? **Java 16, JEP 395**.
- Record pattern preview lần đầu ở Java nào? **Java 19, JEP 405**.
- Record pattern second preview ở Java nào? **Java 20, JEP 432**.
- Record pattern final ở Java nào? **Java 21, JEP 440**.
- Pattern matching for `switch` final ở Java nào? **Java 21, JEP 441**.
- Unnamed patterns `_` final ở Java nào? **Java 22, JEP 456**.

## 16. Tóm tắt ghi nhớ

- **Record ≠ record pattern.** Record là kiểu dữ liệu chính thức từ Java 16; record pattern deconstruct record chỉ chính thức từ Java 21.
- **Java 19 → 20 → 21:** **JEP 405 preview → JEP 432 second preview → JEP 440 final**.
- **Java 17:** dùng `record`, type pattern `instanceof Point point` và accessor; **không** dùng `Point(var x, var y)`.
- **Java 21:** dùng nested record patterns trong `instanceof`/`switch`, không cần `--enable-preview`; pattern matching for switch cũng final ở Java 21.
- **Java 22:** unnamed patterns `_` trở thành chính thức; Java 21 chỉ có preview riêng.
- **Preview migration không phải chỉ xóa một flag:** kiểm tra named patterns lịch sử, enhanced-for, generic inference, source/release và runtime.
- **Muốn chạy đúng:** bảo đảm compiler, target release, preview flags (nếu áp dụng) và runtime nhất quán; test các đường match, null và fallback.

**Tài liệu chính thức:**

- [JEP 359 — Records (Preview, Java 14)](https://openjdk.org/jeps/359)
- [JEP 384 — Records (Second Preview, Java 15)](https://openjdk.org/jeps/384)
- [JEP 395 — Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 405 — Record Patterns (Preview, Java 19)](https://openjdk.org/jeps/405)
- [JEP 432 — Record Patterns (Second Preview, Java 20)](https://openjdk.org/jeps/432)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 443 — Unnamed Patterns and Variables (Preview, Java 21)](https://openjdk.org/jeps/443)
- [JEP 456 — Unnamed Variables & Patterns (Java 22)](https://openjdk.org/jeps/456)
- [Oracle Java 21 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
