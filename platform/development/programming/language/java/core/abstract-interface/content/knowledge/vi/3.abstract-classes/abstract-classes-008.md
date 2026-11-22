# Chuỗi kế thừa qua nhiều lớp trừu tượng trong Java

Khi một lớp trừu tượng kế thừa một lớp trừu tượng khác, Java hình thành **chuỗi kế thừa nhiều tầng** (*multilevel inheritance*). Mỗi tầng có thể kế thừa trạng thái, hành vi đã cài đặt và những phương thức trừu tượng còn phải hoàn thiện. Tầng cuối chỉ trở thành lớp cụ thể khi đáp ứng hết các nghĩa vụ trừu tượng được kế thừa.

Bài này tập trung vào chuỗi **lớp trừu tượng → lớp trừu tượng → lớp cụ thể**, cách Java xác định phương thức phải cài đặt, thứ tự khởi tạo, tính đa hình và cách thiết kế chuỗi dễ bảo trì.

## 1. Mô hình và quy tắc cốt lõi

```java
abstract class A {
    abstract void stepA();
}

abstract class B extends A {
    abstract void stepB();
}

class C extends B {
    @Override
    void stepA() {
        System.out.println("A");
    }

    @Override
    void stepB() {
        System.out.println("B");
    }
}
```

Sơ đồ quan hệ:

```text
A (abstract): stepA() chưa cài đặt
    ↑ extends
B (abstract): kế thừa stepA(), thêm stepB()
    ↑ extends
C (concrete): cài đặt stepA() và stepB()
```

Đọc sơ đồ từ dưới lên: `C extends B`, `B extends A`, vì vậy `C` cũng là một `A` theo quan hệ *is-a*. Java cho phép nhiều **tầng** kế thừa, nhưng mỗi lớp chỉ được `extends` **một lớp cha trực tiếp**; không có kế thừa đa lớp kiểu `class C extends A, B`.

Những điểm cần nhớ:

- Lớp `abstract` có thể kế thừa lớp `abstract` hoặc lớp thường; lớp con của nó cũng có thể tiếp tục là `abstract`.
- Một lớp trừu tượng **không bắt buộc** cài đặt ngay tất cả phương thức trừu tượng kế thừa. Nó có thể cài đặt một phần, thêm nghĩa vụ mới, hoặc không thêm gì.
- Một lớp **không khai báo `abstract`** phải cung cấp cài đặt hợp lệ cho **mọi** phương thức trừu tượng còn tồn đọng trong cả chuỗi. Cài đặt có thể được kế thừa từ lớp cha ở tầng trung gian; không nhất thiết viết lại trong lớp cuối.
- Không thể `new A()` hay `new B()`, dù chúng có constructor. Có thể tạo `new C()` rồi giữ đối tượng bằng biến kiểu `A`, `B` hoặc `C`.
- `abstract` chỉ định một lớp chưa được khởi tạo trực tiếp hoặc một phương thức chưa có phần thân. Một lớp có thể là `abstract` dù **không chứa phương thức trừu tượng nào**.

**Quy tắc xác định nghĩa vụ:** bắt đầu từ lớp cha gốc, theo dõi các phương thức trừu tượng; mỗi cài đặt cụ thể hợp lệ sẽ giải quyết một nghĩa vụ, mỗi khai báo `abstract` mới sẽ thêm nghĩa vụ. Tại lớp cụ thể đầu tiên, danh sách nghĩa vụ chưa giải quyết phải rỗng.

## 2. Mỗi tầng đóng góp điều gì?

| Tầng | Vai trò | Có thể để lại phương thức trừu tượng? | Có thể khởi tạo trực tiếp? |
| --- | --- | --- | --- |
| `A` trừu tượng | Đặt hợp đồng chung, cung cấp dữ liệu/hành vi dùng lại | Có | Không |
| `B extends A` trừu tượng | Chuyên biệt hóa, cài đặt một phần, bổ sung hợp đồng | Có | Không |
| `C extends B` cụ thể | Hoàn tất những phần còn thiếu, tạo đối tượng sử dụng được | Không | Có |

Tầng trung gian không chỉ là một cái tên để kéo dài cây kế thừa. Nó nên gom một tập quy tắc hoặc hành vi chung có ý nghĩa cho **nhiều** lớp cụ thể, ví dụ tài nguyên số kế thừa tài nguyên nói chung rồi được chuyên biệt thành PDF, ảnh hoặc âm thanh.

Một phương thức đã có phần thân ở `A` được `B` và `C` kế thừa bình thường, trừ khi được ghi đè hợp lệ. Một phương thức còn `abstract` ở `A` có thể được `B` cài đặt và khi đó `C` không cần cài đặt lại nó.

## 3. Ví dụ chạy được: ba tầng và cài đặt tăng dần

Lưu toàn bộ chương trình sau vào tệp **`Main.java`**. Các lớp phụ được để cùng tệp và chỉ `Main` là `public` để ví dụ có thể biên dịch độc lập trên Java 17+.

```java
abstract class Resource {
    private final String code;

    protected Resource(String code) {
        this.code = code;
        System.out.println("Resource -> " + code);
    }

    protected String code() {
        return code;
    }

    public abstract String kind();

    public abstract int units();

    public String description() {
        return kind() + ":" + code() + ":" + units();
    }
}

abstract class DigitalResource extends Resource {
    protected DigitalResource(String code) {
        super(code);
        System.out.println("DigitalResource");
    }

    @Override
    public String kind() {
        return "digital";
    }

    public abstract String format();

    public String fullDescription() {
        return description() + ":" + format();
    }
}

final class PdfResource extends DigitalResource {
    private final int pages;

    public PdfResource(String code, int pages) {
        super(code);
        this.pages = pages;
        System.out.println("PdfResource");
    }

    @Override
    public int units() {
        return pages;
    }

    @Override
    public String format() {
        return "PDF";
    }
}

public class Main {
    public static void main(String[] args) {
        DigitalResource digital = new PdfResource("R-07", 12);
        Resource general = digital;

        System.out.println(digital.fullDescription());
        System.out.println(general.description());
    }
}
```

Biên dịch và chạy trong thư mục chứa `Main.java`:

```bash
javac Main.java
java Main
```

Kết quả chuẩn:

```text
Resource -> R-07
DigitalResource
PdfResource
digital:R-07:12:PDF
digital:R-07:12
```

**Phân tích lần lượt các tầng:**

1. `Resource` khai báo hai nghĩa vụ: `kind()` và `units()`. Nó cũng định nghĩa constructor, trường `code` và phương thức cụ thể `description()`. Bên trong `description()`, lời gọi `kind()` và `units()` có thể dẫn đến cài đặt ở lớp con.
2. `DigitalResource` vẫn là `abstract`, nhưng đã cài đặt `kind()`. Nó kế thừa nghĩa vụ `units()` chưa giải quyết và thêm nghĩa vụ `format()`. Phương thức `fullDescription()` tái sử dụng `description()` ở tầng gốc.
3. `PdfResource` giải quyết `units()` và `format()`. Vì `kind()` đã được tầng giữa cài đặt nên nó trở thành lớp cụ thể hợp lệ. `final` ở đây là lựa chọn thiết kế nhằm không cho phép lớp khác kế thừa tiếp `PdfResource`; nó không phải yêu cầu của chuỗi trừu tượng.
4. Dòng `DigitalResource digital = new PdfResource(...)` là đa hình: **kiểu tham chiếu** là `DigitalResource`, **kiểu đối tượng thực tế** là `PdfResource`. Dòng `Resource general = digital` không tạo thêm đối tượng, chỉ tạo thêm tham chiếu tới cùng đối tượng.

Hai lần in mô tả đều dùng `kind()` của `DigitalResource` và `units()` của `PdfResource` thông qua **dynamic dispatch**. Mã ở tầng `Resource` không cần biết tên lớp cụ thể nào sẽ thực hiện các phương thức đó.

## 4. Phương thức trừu tượng được “truyền” qua các tầng như thế nào?

Xét chuỗi nghĩa vụ từ ví dụ:

```text
Resource:
    kind()    -> abstract
    units()   -> abstract

DigitalResource:
    kind()    -> implemented
    units()   -> inherited abstract
    format()  -> new abstract

PdfResource:
    kind()    -> inherited implementation
    units()   -> implemented
    format()  -> implemented
```

Đừng hiểu nhầm rằng chỉ những phương thức `abstract` **được viết trực tiếp** trong lớp cha gần nhất mới cần cài đặt. `PdfResource` còn chịu nghĩa vụ `units()` bắt nguồn từ `Resource`, dù `DigitalResource` không khai báo lại phương thức đó.

Nếu bỏ `units()` khỏi `PdfResource` mà giữ `PdfResource` là lớp cụ thể, chương trình **không biên dịch được**: lớp đó chưa cài đặt đủ hợp đồng trừu tượng. Hai hướng sửa hợp lệ là cung cấp `units()` trong `PdfResource` hoặc giữ lớp này là `abstract` để lớp con khác tiếp tục hoàn thiện; lựa chọn phụ thuộc mục đích thiết kế.

Một tầng trung gian cũng có thể cài đặt **toàn bộ** phương thức trừu tượng được thừa kế nhưng vẫn tự khai báo `abstract`: điều này hợp lệ, chẳng hạn khi muốn ngăn khởi tạo trực tiếp hoặc dự định bổ sung quy tắc ở lớp con. Từ khóa `abstract` trên lớp và số lượng phương thức `abstract` không có quan hệ một-một.

## 5. Override và trừu tượng hóa lại trong chuỗi

Các quy tắc override vẫn áp dụng ở mọi tầng: chữ ký phải tương thích, không được thu hẹp quyền truy cập hoặc mở rộng checked exception trái quy tắc; `@Override` giúp phát hiện sai chữ ký. Phương thức `final` không thể override, `private` không tạo hook kế thừa và `static` dùng hiding thay vì dynamic dispatch. Trách nhiệm của lớp cụ thể và checklist chữ ký được phân tích sâu hơn trong bài về hoàn thiện triển khai.

Một trường hợp đáng chú ý là lớp trung gian có thể **trừu tượng hóa lại** một phương thức có thân ở lớp cha (miễn phương thức đó không `final`) để buộc các lớp cụ thể bên dưới cung cấp cách làm riêng:

```java
abstract class Base {
    String status() {
        return "DEFAULT";
    }
}

abstract class Specialized extends Base {
    @Override
    abstract String status();
}

final class Ready extends Specialized {
    @Override
    String status() {
        return "READY";
    }
}
```

Đoạn mã chỉ minh họa khai báo lớp, không có `main`. `Ready` phải cài đặt `status()` vì `Specialized` đã khai báo lại phương thức đó là `abstract`, dù `Base` từng có phần thân. Dùng kỹ thuật này có chủ đích vì nó làm hợp đồng nghiêm ngặt hơn.

## 6. Constructor vẫn chạy xuyên suốt chuỗi

`abstract` không cấm constructor. Khi tạo `new PdfResource("R-07", 12)`, constructor chạy theo chuỗi từ `Object` đến `Resource`, `DigitalResource`, rồi `PdfResource`; các dòng stdout trong ví dụ mục 3 thể hiện chính thứ tự này. Mỗi tầng phải gọi được constructor cha phù hợp, tường minh bằng `super(...)` hoặc qua `super()` ngầm định khi có constructor không đối số khả dụng.

Không lặp lại ví dụ bẫy khởi tạo ở đây: quy tắc về thứ tự initializer và nguy cơ gọi phương thức override khi trường lớp con chưa sẵn sàng thuộc bài chuyên về constructor. Trong chuỗi kế thừa, hãy để constructor khởi tạo trạng thái và thực hiện hành vi đa hình sau khi đối tượng được xây dựng xong.

## 7. Kiểu tham chiếu, phương thức nhìn thấy và ép kiểu

Với đối tượng được khai báo như sau:

```java
PdfResource pdf = new PdfResource("R-08", 8);
DigitalResource digital = pdf;
Resource resource = pdf;
```

Các dòng trên là đoạn minh họa đặt trong ngữ cảnh các lớp ở mục 3. Cả ba biến cùng trỏ tới **một** đối tượng `PdfResource`, nhưng kiểu tham chiếu quyết định các thành viên mà trình biên dịch cho phép gọi:

| Biến | Gọi được theo kiểu khai báo | Không gọi trực tiếp được |
| --- | --- | --- |
| `pdf` | `description()`, `fullDescription()`, `format()`, `units()` | — |
| `digital` | `description()`, `fullDescription()`, `format()`, `units()` | — |
| `resource` | `description()`, `kind()`, `units()` | `format()`, `fullDescription()` |

`resource.description()` vẫn chạy các cài đặt override ở đối tượng `PdfResource`/`DigitalResource`, mặc dù `resource` không gọi trực tiếp được `format()`. **Quyền gọi tại thời điểm biên dịch** và **cài đặt được chọn tại thời điểm chạy** là hai vấn đề khác nhau.

Nếu thật sự cần thao tác đặc thù với tầng giữa, có thể kiểm tra kiểu trước khi ép:

```java
if (resource instanceof DigitalResource digitalResource) {
    System.out.println(digitalResource.format());
}
```

Đây là cú pháp *pattern matching for instanceof* được hỗ trợ trên Java 17. Trong thiết kế tốt, hãy ưu tiên đặt thao tác chung cần thiết trên hợp đồng của tầng phù hợp, thay vì liên tục `instanceof`/ép kiểu.

## 8. Thiết kế chuỗi trừu tượng hợp lý

Một chuỗi nhiều tầng có ích khi từng tầng đại diện cho **một khái niệm chuyên biệt có nghĩa**:

```text
Resource (tất cả tài nguyên)
    └── DigitalResource (tài nguyên số có định dạng)
            ├── PdfResource
            └── ImageResource
```

Ví dụ, `Resource` sở hữu định danh, `DigitalResource` biết đặc trưng chung của tài nguyên số, còn `PdfResource` và `ImageResource` cài đặt chi tiết riêng. Tầng giữa đáng tồn tại nếu nhiều lớp cùng dùng logic của nó.

Trong khi thiết kế, cần:

1. Xác định bất biến và dữ liệu chung ở lớp gốc; dùng `private` cho trạng thái cần bảo vệ, mở phương thức `protected`/`public` khi thật sự cần.
2. Đặt phương thức trừu tượng ở tầng thấp nhất có thể diễn đạt chính xác **nghĩa vụ chung**, tránh ép các lớp không liên quan triển khai hành vi vô nghĩa.
3. Cài đặt logic dùng chung một lần ở tầng phù hợp; dùng phương thức `final` khi muốn giữ bất biến trong thuật toán và không cho lớp dưới ghi đè bước quan trọng.
4. Đảm bảo các lớp con giữ đúng hợp đồng của cha: mọi nơi kỳ vọng `Resource` vẫn phải làm việc đúng với `PdfResource`. Không thay đổi ý nghĩa `units()` giữa các nhánh đến mức người dùng API hiểu sai.
5. Tránh tạo tầng `abstract` chỉ để đặt tên cho một bước chuyển tiếp hoặc để giảm vài dòng mã. Mỗi tầng thêm độ phụ thuộc, khiến việc đọc và thay đổi cây kế thừa khó hơn.
6. Nếu các loại đối tượng chỉ cần chia sẻ **khả năng** mà không có một quan hệ *is-a* chặt chẽ, cân nhắc `interface`; nếu chỉ muốn tái sử dụng một thành phần, cân nhắc **composition**. Java vẫn cho phép một lớp `extends` một lớp và `implements` nhiều interface.

Một mẫu hữu ích là **Template Method**: tầng trừu tượng triển khai quy trình ổn định và gọi những bước `protected abstract` để lớp con hoàn thiện. Cần tránh gọi quy trình có thể override từ constructor và định nghĩa rõ tiền điều kiện, hậu điều kiện của từng bước.

## 9. Những lỗi và ngộ nhận thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lớp cuối báo chưa cài đặt phương thức trừu tượng | Nghĩa vụ ở tầng ông/bà vẫn tồn tại | Rà soát toàn chuỗi; cài đặt đủ phương thức hoặc khai báo lớp tiếp tục `abstract` |
| `new` lớp trung gian trừu tượng bị lỗi | Không thể khởi tạo trực tiếp lớp `abstract` | Khởi tạo lớp cụ thể và giữ tham chiếu bằng kiểu trừu tượng |
| Lỗi constructor `super()` | Cha không có constructor không tham số khả dụng | Gọi `super(args)` phù hợp trong constructor con |
| Override bị lỗi biên dịch | Sai chữ ký, giảm quyền truy cập, không phù hợp kiểu trả về/`throws`, hoặc đụng phương thức `final` | So lại khai báo chính xác ở tất cả tầng liên quan, dùng `@Override` |
| Gọi phương thức riêng của lớp con qua biến cha không biên dịch | Kiểu tham chiếu không khai báo phương thức đó | Đưa hành vi chung lên API cha hoặc kiểm tra kiểu rồi ép khi cần |
| Giá trị trường con bất ngờ là `null`/`0` trong constructor cha | Constructor cha gọi phương thức bị override trước khi trường con khởi tạo | Không dispatch tới phương thức override trong constructor |
| Cây kế thừa quá sâu, nhiều lớp chỉ truyền tiếp không thêm ý nghĩa | Mô hình hóa sai trách nhiệm, lạm dụng kế thừa | Giảm tầng, tách khả năng thành interface hoặc thành phần composition |

Một số ranh giới quan trọng: Java **không** cho kế thừa nhiều lớp trực tiếp; `abstract` không có nghĩa mọi phương thức đều trừu tượng; và `super` cho phép truy cập hành vi cha phù hợp nhưng không biến một phương thức `abstract` chưa có phần thân thành thứ có thể thực thi.

## 10. Tự kiểm tra kiến thức

**Bài 1 — xác định nghĩa vụ.** Giả sử `A` khai báo `abstract void x()` và `abstract void y()`. `B extends A` (vẫn `abstract`) chỉ cài đặt `x()` rồi thêm `abstract void z()`. Lớp cụ thể `C extends B` phải cài đặt những phương thức nào?

<details>
<summary>Đáp án và lý do</summary>

`C` phải cài đặt `y()` và `z()`. `x()` đã được `B` cung cấp phần thân nên được `C` kế thừa. Trừ khi `C` muốn thay đổi hành vi `x()`, không cần override lại.
</details>

**Bài 2 — đa hình.** Với chương trình mục 3, thay khai báo bằng `Resource value = new PdfResource("R-09", 5);`. `value.description()` có dùng `Resource.kind()` không? Có thể gọi `value.fullDescription()` trực tiếp không?

<details>
<summary>Đáp án và lý do</summary>

`Resource` chỉ khai báo `kind()` là trừu tượng; khi chạy, `description()` gọi `kind()` của `DigitalResource` và `units()` của `PdfResource`. Không thể gọi trực tiếp `value.fullDescription()` vì kiểu khai báo `Resource` không có phương thức đó. Có thể gọi qua tham chiếu `DigitalResource` hoặc phép ép kiểu hợp lệ.
</details>

**Bài 3 — mở rộng.** Tạo `abstract class DocumentResource extends DigitalResource` bổ sung phương thức `abstract String category()`. Sau đó tạo `final class InvoicePdf extends DocumentResource` để hoàn thành `units()`, `format()` và `category()`. Giải thích vì sao `kind()` không cần viết lại. Hãy tự in thứ tự constructor và kiểm tra `description()` khi giữ đối tượng bằng biến `Resource`.

**Checklist trước khi chốt một chuỗi kế thừa:** mọi tầng có trách nhiệm rõ ràng; nghĩa vụ `abstract` được theo dõi qua toàn chuỗi; lớp cuối thực hiện đủ hợp đồng; constructor gọi `super(...)` hợp lệ; không gọi hành vi override trong constructor; API giữ đúng tính đa hình và các quy tắc override.