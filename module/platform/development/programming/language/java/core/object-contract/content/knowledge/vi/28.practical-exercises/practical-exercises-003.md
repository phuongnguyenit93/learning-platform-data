# Thực hành: sửa lớp có `equals(MyType)` nhưng chưa ghi đè `equals(Object)`

## 1. Bài toán cần sửa

Bạn nhận một lớp Java biểu diễn khóa định danh của một bản sách. Hai đối tượng có cùng mã sách và cùng lần hiệu đính phải được xem là bằng nhau về mặt giá trị. Lớp hiện có `equals(BookKey)` và đôi khi thử trực tiếp `a.equals(b)` cho kết quả `true`. Tuy nhiên, khi truyền các đối tượng đó cho API nhận `Object` hoặc đưa vào `List`, `Set`, phép so sánh lại thất bại.

Mục tiêu là **sửa hợp đồng bình đẳng đối tượng** để các lệnh gọi thông qua kiểu `Object` và các API collection đều nhận được phép so sánh giá trị đúng. Đây là lỗi điển hình ở ranh giới giữa *overloading* (nạp chồng) và *overriding* (ghi đè).

Sau khi thực hành, bạn sẽ có thể:
- Nhìn chữ ký phương thức để nhận ra `equals(MyType)` **không** ghi đè `Object.equals(Object)`.
- Chỉ ra tại sao phép gọi trực tiếp trông đúng nhưng `List.contains` và `HashSet.contains` có thể sai.
- Ghi đè chuẩn `public boolean equals(Object obj)` và `public int hashCode()`, dùng `@Override` để trình biên dịch kiểm tra.
- Kiểm tra các thuộc tính cơ bản của `equals` cùng khả năng dùng khóa giá trị trong hash collection.
- Nhận diện các lỗi còn lại liên quan đến `null`, tính đối xứng, phân lớp và trường có thể thay đổi.

## 2. Phân tích mã lỗi: cùng tên chưa đủ để ghi đè

Đây là lớp lỗi, xét riêng các thành phần quyết định phép so sánh:

```java
import java.util.Objects;

final class BrokenBookKey {
    private final String code;
    private final int revision;

    BrokenBookKey(String code, int revision) {
        this.code = Objects.requireNonNull(code);
        this.revision = revision;
    }

    // Nạp chồng! Tham số là BrokenBookKey, không phải Object.
    public boolean equals(BrokenBookKey other) {
        return other != null
                && revision == other.revision
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(code, revision);
    }
}
```

Hãy đọc đúng hai chữ ký:

```java
public boolean equals(BrokenBookKey other) // Phương thức mới: overload
public boolean equals(Object obj)          // Chữ ký cần override từ Object
```

Phương thức thứ hai ở đây là **chữ ký cần có**, không phải phương thức đang tồn tại trong lớp lỗi. Vì lớp mới chỉ khai báo `equals(BrokenBookKey)`, nó vẫn kế thừa `Object.equals(Object)`, nghĩa là khi lời gọi được ràng buộc với chữ ký `equals(Object)` thì bình đẳng mặc định là **cùng đối tượng (identity)**.

Việc ghi đè `hashCode()` trong lớp lỗi cố ý làm ví dụ rõ hơn: **chỉ khắc phục hash code không thể thay thế cho việc ghi đè `equals(Object)`**. Hai đối tượng khác tham chiếu có cùng giá trị và cùng mã băm vẫn có thể bị so sánh là không bằng nhau.

### Vì sao hai lời gọi chọn phương thức khác nhau?

```java
BrokenBookKey a = new BrokenBookKey("JAVA-21", 2);
BrokenBookKey b = new BrokenBookKey("JAVA-21", 2);
Object viewedAsObject = b;

boolean direct = a.equals(b);               // Chọn equals(BrokenBookKey)
boolean viaObject = a.equals(viewedAsObject); // Chọn equals(Object)
```

- Trong `a.equals(b)`, kiểu tĩnh (*compile-time type*) của `b` là `BrokenBookKey`; trình biên dịch chọn overload nhận `BrokenBookKey` vì cụ thể hơn.
- Trong `a.equals(viewedAsObject)`, kiểu tĩnh của tham số là `Object`; trình biên dịch chọn chữ ký `equals(Object)` và lúc chạy không có override ở `BrokenBookKey`, nên thực thi `Object.equals(Object)`.
- Sự lựa chọn giữa **các overload** diễn ra trong lúc biên dịch; việc chọn phần cài đặt **override** phù hợp với đối tượng nhận diễn ra lúc chạy. Hai cơ chế không thay thế nhau.
- Phép thử chỉ dùng `a.equals(b)` với hai biến đều có kiểu `BrokenBookKey` có thể che giấu lỗi.

Một cách dò lỗi nhanh: thử đặt `@Override` trước `equals(BrokenBookKey other)`. Trình biên dịch báo lỗi vì phương thức này không override phương thức nào trong lớp cha. **Không sửa lỗi đó bằng cách xóa `@Override`; phải đổi đúng chữ ký sang `equals(Object)`.**

## 3. Cách sửa tối thiểu và chính xác

Với lớp **final** có ý nghĩa bình đẳng theo hai trường `code` và `revision`, cài đặt chuẩn như sau:

```java
import java.util.Objects;

public final class BookKey {
    private final String code;
    private final int revision;

    public BookKey(String code, int revision) {
        this.code = Objects.requireNonNull(code, "code");
        this.revision = revision;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof BookKey other)) {
            return false;
        }
        return revision == other.revision
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(code, revision);
    }
}
```

Lưu tệp trên thành `BookKey.java` và biên dịch bằng `javac BookKey.java` với JDK 17 trở lên. Đây là một lớp thư viện hoàn chỉnh, **không có `main`** nên bản thân nó không in stdout.

Ý nghĩa từng phần:

1. `@Override` xác nhận với trình biên dịch rằng chữ ký đúng là `equals(Object)`. Nếu viết sai kiểu tham số hoặc phạm vi truy cập, lỗi được phát hiện sớm.
2. `this == obj` nhận biết nhanh cùng một tham chiếu; nhánh này luôn trả về `true`, giữ tính *phản xạ*.
3. `obj instanceof BookKey other` loại `null` và đối tượng khác kiểu; `other` là biến nhận kiểu (pattern variable) của Java 16+, phù hợp Java 17.
4. Chỉ so sánh **các trường cấu thành danh tính giá trị**: cùng `revision` và cùng `code`. Vì constructor loại `null`, `code.equals(other.code)` an toàn.
5. `hashCode()` sử dụng **chính các trường được kiểm tra trong `equals`**. Nếu `a.equals(b)` là `true`, bắt buộc `a.hashCode() == b.hashCode()`.
6. Khai báo lớp `final` giúp không có subclass thêm trường hoặc thay đổi quy tắc bình đẳng, giảm nguy cơ vi phạm tính đối xứng.

Nếu chính bài tập yêu cầu giữ lại `equals(BookKey)` vì tương thích mã nguồn cũ, có thể cho overload đó **ủy quyền** về đường kiểm tra chuẩn:

```java
public boolean equals(BookKey other) {
    return equals((Object) other);
}
```

Đoạn trên là phương thức bổ sung tùy chọn **bên trong lớp đã ghi đè `equals(Object)`**. Ép `(Object)` là có chủ đích để chọn đúng overload; không bắt buộc giữ `equals(BookKey)` trong thiết kế mới và tránh lặp logic bình đẳng ở hai nơi.

## 4. Chương trình chứng minh lỗi và kết quả sau sửa

Ví dụ dưới đây là **một chương trình độc lập** với hai lớp lồng nhau: một lớp vẫn bị overload và một lớp đã sửa. Nó kiểm tra phép gọi thông qua `Object`, `List.contains`, `HashSet.contains` và mã băm.

Tạo tệp `EqualsOverloadRepairDemo.java`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class EqualsOverloadRepairDemo {
    static final class BrokenBookKey {
        private final String code;
        private final int revision;

        BrokenBookKey(String code, int revision) {
            this.code = Objects.requireNonNull(code);
            this.revision = revision;
        }

        // Sai mục tiêu: overload, không phải override Object.equals(Object).
        public boolean equals(BrokenBookKey other) {
            return other != null
                    && revision == other.revision
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, revision);
        }
    }

    static final class FixedBookKey {
        private final String code;
        private final int revision;

        FixedBookKey(String code, int revision) {
            this.code = Objects.requireNonNull(code);
            this.revision = revision;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof FixedBookKey other)) return false;
            return revision == other.revision
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, revision);
        }
    }

    public static void main(String[] args) {
        BrokenBookKey brokenA = new BrokenBookKey("JAVA-21", 2);
        BrokenBookKey brokenB = new BrokenBookKey("JAVA-21", 2);
        Object brokenAsObject = brokenB;
        Set<BrokenBookKey> brokenSet = new HashSet<>();
        brokenSet.add(brokenA);

        System.out.println("BROKEN");
        System.out.println("typedEquals=" + brokenA.equals(brokenB));
        System.out.println("objectEquals=" + brokenA.equals(brokenAsObject));
        System.out.println("listContains=" + List.of(brokenA).contains(brokenB));
        System.out.println("setContains=" + brokenSet.contains(brokenB));
        System.out.println("sameHash=" + (brokenA.hashCode() == brokenB.hashCode()));

        FixedBookKey fixedA = new FixedBookKey("JAVA-21", 2);
        FixedBookKey fixedB = new FixedBookKey("JAVA-21", 2);
        FixedBookKey different = new FixedBookKey("JAVA-21", 3);
        Object fixedAsObject = fixedB;
        Set<FixedBookKey> fixedSet = new HashSet<>();
        fixedSet.add(fixedA);

        System.out.println("FIXED");
        System.out.println("typedEquals=" + fixedA.equals(fixedB));
        System.out.println("objectEquals=" + fixedA.equals(fixedAsObject));
        System.out.println("listContains=" + List.of(fixedA).contains(fixedB));
        System.out.println("setContains=" + fixedSet.contains(fixedB));
        System.out.println("sameHash=" + (fixedA.hashCode() == fixedB.hashCode()));
        System.out.println("differentRevision=" + fixedA.equals(different));
        System.out.println("equalsNull=" + fixedA.equals(null));
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac EqualsOverloadRepairDemo.java
java EqualsOverloadRepairDemo
```

Stdout chính xác (chương trình trên chỉ dùng các giá trị xác định):

```text
BROKEN
typedEquals=true
objectEquals=false
listContains=false
setContains=false
sameHash=true
FIXED
typedEquals=true
objectEquals=true
listContains=true
setContains=true
sameHash=true
differentRevision=false
equalsNull=false
```

**Giải thích kết quả trước sửa:** `brokenA.equals(brokenB)` dùng overload nên trả `true`. Ngược lại, `brokenA.equals(brokenAsObject)` gọi chữ ký `equals(Object)` kế thừa nên `false`. Các Collection API kiểm tra bình đẳng qua giao diện `Object.equals(Object)`, vì vậy đối tượng thứ hai dù có cùng giá trị vẫn không được tìm thấy. `sameHash=true` chỉ cho thấy hai mã băm bằng nhau, không tự khiến `equals(Object)` đúng.

**Giải thích kết quả sau sửa:** `FixedBookKey.equals(Object)` được dispatch kể cả khi đối số hoặc biến được nhìn bằng kiểu `Object`. Cả `List.contains` lẫn `HashSet.contains` có thể tìm đối tượng khác tham chiếu nhưng bằng nhau về giá trị. Mã băm thống nhất với phép so sánh; `revision` khác nhau không bằng nhau; `null` không bằng đối tượng hợp lệ.

Trong `HashSet`, mã băm trước tiên giúp xác định nơi tìm kiếm, còn `equals(Object)` xác nhận hai khóa có thực sự bằng nhau hay không. Có cùng mã băm **không đồng nghĩa** hai phần tử bằng nhau; *hash collision* hợp lệ. Có `equals` đúng mà `hashCode` sai cũng có thể gây lỗi lookup vì hai đối tượng bằng nhau bị đặt vào các bucket khác nhau.

## 5. Hợp đồng `equals(Object)` và `hashCode()` cần giữ

Với các tham chiếu khác `null`, hợp đồng chính của `equals` gồm:

| Thuộc tính | Điều cần đảm bảo | Kiểm tra gợi ý |
| --- | --- | --- |
| Phản xạ (*reflexive*) | `x.equals(x)` là `true` | So sánh một instance với chính nó |
| Đối xứng (*symmetric*) | `x.equals(y)` và `y.equals(x)` cho cùng kết quả | Kiểm tra hai chiều, cả với kiểu con nếu cho phép kế thừa |
| Bắc cầu (*transitive*) | Nếu `x=y` và `y=z` thì `x=z` về nghĩa `equals` | Tạo ba instance có cùng trường giá trị |
| Nhất quán (*consistent*) | Kết quả giữ nguyên khi trạng thái dùng cho bình đẳng không đổi | Gọi nhiều lần trước khi sửa dữ liệu |
| So với null | `x.equals(null)` là `false` | Kiểm tra cụ thể qua chữ ký `Object` |

Với `hashCode`, quy tắc bắt buộc là **hai đối tượng bằng nhau theo `equals` phải có hash code bằng nhau** trong cùng một lần quan sát trạng thái. Chiều ngược lại **không bắt buộc**. Nếu hai đối tượng không bằng nhau, mã băm của chúng vẫn có thể trùng nhau.

Trong lớp khóa giá trị, nên ưu tiên các trường `final` và kiểu giá trị bất biến. Khi dùng một đối tượng làm phần tử `HashSet` hoặc khóa `HashMap`, **không thay đổi các trường tham gia `equals/hashCode` trong khi đối tượng đang được lưu**: nếu không, hash bucket cũ và mã băm mới có thể lệch nhau, khiến tìm kiếm thất bại ngay cả với chính tham chiếu đó.

## 6. Checklist sửa lớp thật tại dự án

Áp dụng trực tiếp lên lớp hiện đang có `equals(MyType)`:

1. **Xác định ý nghĩa bình đẳng.** Đặt câu hỏi “Hai instance nào được xem là cùng giá trị?” và ghi rõ những trường tham gia. Không mặc định so sánh mọi trường nếu có trường chỉ là cache, timestamp hoặc metadata không liên quan danh tính.
2. **Thay chữ ký sai.** Viết `@Override public boolean equals(Object obj)`; bảo đảm tên `equals`, chữ `Object` của `java.lang.Object`, kiểu trả về `boolean` và phạm vi `public`.
3. **Xử lý cùng tham chiếu, null và khác kiểu.** Trả `true` nhanh cho `this == obj`, trả `false` khi không đúng kiểu giá trị.
4. **So sánh nội dung theo loại trường.** Kiểu nguyên thủy dùng toán tử `==`; đối tượng dùng `Objects.equals(a, b)` khi có thể null hoặc `a.equals(b)` khi được bảo đảm khác null; mảng cần `Arrays.equals` hoặc `Arrays.deepEquals` theo cấu trúc dữ liệu, không dùng so sánh tham chiếu nếu cần giá trị.
5. **Ghi đè `hashCode()` đồng bộ.** Cùng tập trường và cùng quy tắc so sánh; với mảng cần xét `Arrays.hashCode`/`Arrays.deepHashCode` cho tương ứng.
6. **Rà soát caller.** Tìm nơi gọi `equals(MyType)`. Khi không cần API overload, bỏ phương thức đó; nếu bắt buộc giữ để tương thích, cho ủy quyền đến `equals(Object)` và tránh cài đặt hai thuật toán khác nhau.
7. **Thử dưới kiểu `Object` và qua collection.** Kiểm tra `Object ref = b; a.equals(ref)`, `List.contains(b)`, `HashSet.contains(b)`, `HashMap.get(b)` (khi đã thêm khóa bằng giá trị). Đừng chỉ thử `a.equals(b)` với hai biến kiểu cụ thể.
8. **Kiểm tra hợp đồng hai chiều và biến thể dữ liệu.** Bao gồm chính nó, instance bằng giá trị, instance khác một trường, `null`, đối tượng khác kiểu và trường hợp được phép kế thừa.

Ví dụ test thủ công không cần thư viện ngoài, dùng cùng lớp `BookKey` ở mục 3:

```java
BookKey a = new BookKey("JAVA-21", 2);
BookKey b = new BookKey("JAVA-21", 2);
BookKey c = new BookKey("JAVA-21", 2);
BookKey other = new BookKey("JAVA-21", 3);

if (!a.equals(a)) throw new AssertionError("reflexive");
if (!a.equals(b) || !b.equals(a)) throw new AssertionError("symmetric");
if (!(a.equals(b) && b.equals(c) && a.equals(c))) {
    throw new AssertionError("transitive");
}
if (a.equals(other) || a.equals(null) || a.equals("JAVA-21")) {
    throw new AssertionError("non-equal case");
}
if (a.hashCode() != b.hashCode()) throw new AssertionError("hash consistency");
if (!java.util.Set.of(a).contains(b)) {
    throw new AssertionError("collection lookup");
}
```

Đây là **đoạn kiểm chứng cần đặt trong phương thức** (ví dụ `main` hoặc test), không phải chương trình độc lập; các kiểm tra dùng `AssertionError` trực tiếp nên chạy ngay cả khi JVM không được bật tùy chọn `-ea`.

## 7. Các lựa chọn và bẫy đáng chú ý

### `instanceof`, `getClass()` và kế thừa

Ví dụ `BookKey` là lớp `final`; kiểm tra `instanceof BookKey` tương ứng với phạm vi các instance của lớp đó. Nếu lớp **không final** và có subclass thêm trường, phép so sánh giữa lớp cha và lớp con dễ phá tính đối xứng hoặc bắc cầu. Cần chọn và kiểm thử một chính sách kế thừa rõ ràng:

- `getClass() == obj.getClass()` chỉ chấp nhận **cùng runtime class**, thường phù hợp bình đẳng có phân biệt chính xác kiểu, nhưng loại cả subclass hoặc proxy.
- `instanceof` chấp nhận kiểu con; phải bảo đảm các lớp con không thay đổi cách so sánh theo hướng làm vi phạm hợp đồng.
- Đánh dấu lớp giá trị `final` hoặc chọn một thiết kế bình đẳng nhất quán thường dễ kiểm soát hơn. Không tự thay `getClass` bằng `instanceof` trong code đang dùng polymorphism mà chưa đánh giá hệ quả.

### Sự nhầm lẫn khác với overload

- `equals(MyType)` và `equals(Object)` có thể cùng tồn tại, nhưng overload thường gây bất ngờ vì kết quả khác nhau tùy kiểu tĩnh của biến. Nếu giữ cả hai, bảo đảm chúng cùng quy tắc.
- `equals(Object)` mà quên `@Override` vẫn có thể hoạt động nếu chữ ký chính xác; `@Override` giúp chặn lỗi chữ ký và nên được dùng.
- Ghi đè `equals(Object)` nhưng quên `hashCode()` có thể khiến `HashMap`/`HashSet` hoạt động sai với đối tượng bằng giá trị.
- So sánh `String` bằng `==` kiểm tra cùng tham chiếu, không kiểm tra nội dung. Với khóa bản sách, dùng `String.equals` hoặc `Objects.equals`.
- `Objects.equals(a,b)` chỉ gọi `equals(Object)` đúng theo hợp đồng, nên không tự chữa được lớp có mỗi `equals(MyType)`.
- Không sử dụng `System.identityHashCode` để xây `hashCode` cho lớp có equality theo giá trị.

### Khi nào dùng `record`?

Nếu mục tiêu là một lớp mang dữ liệu bất biến, không có quy tắc đặc thù và các thành phần phù hợp làm danh tính, Java 17 có `record`:

```java
public record BookKeyRecord(String code, int revision) {
    public BookKeyRecord {
        java.util.Objects.requireNonNull(code, "code");
    }
}
```

Record tự sinh `equals(Object)` và `hashCode()` dựa trên thành phần đã khai báo, giúp tránh lỗi bỏ quên override. Đây là lựa chọn thiết kế mới, **không phải sửa chữa bắt buộc cho một lớp hiện hữu** (đặc biệt nếu cần kế thừa từ class khác hoặc có yêu cầu API/serialization riêng).

## 8. Câu hỏi tự kiểm tra và bài tập nhỏ

1. **Tại sao `x.equals(y)` là `true` nhưng `((Object)x).equals(y)` là `false` trước sửa?** Vì lời gọi đầu dùng overload `equals(MyType)`, còn lời gọi sau chỉ nhìn thấy `equals(Object)` và lớp chưa override nó.
2. **Chỉ đổi `equals(MyType)` thành `equals(Object)` đã đủ chưa?** Chưa; phải bảo đảm logic so sánh giá trị đúng và `hashCode()` tuân theo cùng trường, đồng thời kiểm tra các thuộc tính của hợp đồng.
3. **Hai đối tượng có hash code bằng nhau thì `equals` phải trả `true`?** Không. Trùng hash là điều được phép với các đối tượng không bằng nhau.
4. **Vì sao thêm `@Override` là một thao tác debug tốt?** Compiler xác minh phương thức thực sự ghi đè, nhờ đó phát hiện chữ ký `equals(MyType)` sai.
5. **Nếu thay `revision` từ 2 thành 3, đối tượng trong `HashSet` có thể gặp vấn đề gì?** Hash code và phép bằng nhau thay đổi khi object đã nằm trong một bucket cũ; nên bất biến các trường liên quan equality.

**Bài thực hành mở rộng:** Tự bổ sung một trường `region` vào `BookKey` và quyết định liệu khu vực có cấu thành danh tính bản sách hay không. Cập nhật `equals(Object)` và `hashCode()` cùng một lúc, viết ít nhất hai đối tượng khác `region` để chứng minh quy tắc mà bạn chọn. Kiểm tra qua biến `Object` và `HashSet.contains`, rồi thay đổi cách nhìn về `region` và quan sát sự khác biệt.

**Điểm mấu chốt:** Khi cần so sánh giá trị của đối tượng Java trong mã chung và collection, **chữ ký bắt buộc là `public boolean equals(Object)`**. `equals(MyType)` chỉ là overload; một phép gọi trực tiếp thành công chưa chứng minh hợp đồng của `Object` đã được ghi đè.

## Tài liệu tham khảo

- [Java SE 21 — `Object.equals(Object)` và `Object.hashCode()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html).
- [Java SE 21 — `Set` và các điều kiện về phần tử](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).
- [Java SE 21 — `HashSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).
- [Java Language Specification — Overriding và hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8).
- [Java Language Specification — Method invocation: tìm và chọn phương thức](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12).