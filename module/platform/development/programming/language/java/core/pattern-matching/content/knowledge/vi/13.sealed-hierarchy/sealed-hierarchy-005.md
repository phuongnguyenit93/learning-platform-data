# Non-sealed subtype phá vỡ tính đóng của sealed hierarchy

> **Module:** Java Core Pattern Matching → Sealed hierarchy. Trọng tâm là tác dụng của từ khóa **`non-sealed`** đối với khả năng mở rộng hệ phân cấp và việc chứng minh `switch` exhaustive. Phần kế thừa sealed/non-sealed dùng quy tắc Java 17+ (JEP 409); ví dụ pattern matching trong `switch` dùng **Java 21+** (JEP 441) để không cần preview.

## Mục tiêu

Học xong bài này, bạn có thể:

- Phân biệt **`sealed`**, **`final`** và **`non-sealed`** trên những lớp/interface được phép kế thừa trực tiếp một sealed type.
- Chỉ ra chính xác **phần nào của cây kế thừa vẫn đóng** và **nhánh nào được mở lại**; không nhầm “parent sealed” với “mọi hậu duệ đều cố định”.
- Giải thích vì sao một `non-sealed` subtype có thể sinh thêm các hậu duệ mới mà không sửa `permits` của sealed root.
- Viết một **pattern switch exhaustive** trên sealed root **dù có nhánh non-sealed**, bằng cách bao phủ **toàn bộ kiểu của nhánh mở** thay vì chỉ liệt kê vài lớp con đã biết.
- Nhận diện lỗi compile time khi thiếu nhánh mở, lỗi dominance khi đặt nhánh tổng quát trước nhánh cụ thể, và rủi ro khi phụ thuộc vào danh sách hậu duệ hiện tại.
- Đưa ra tiêu chí thiết kế sealed hierarchy cho domain đóng hoặc điểm mở rộng/plugin.

## 1. Sealed hierarchy đóng những gì?

Một **sealed class** hoặc **sealed interface** giới hạn **những kiểu có quyền kế thừa hoặc implement trực tiếp** nó. Java 17 cho phép khai báo rõ trong mệnh đề `permits`:

~~~java
sealed interface Notice permits TextNotice, Extension {
}

record TextNotice(String text) implements Notice {
}

non-sealed class Extension implements Notice {
}
~~~

Các đoạn trên là **minh họa khai báo kiểu trong cùng package/module thích hợp**, chưa phải chương trình độc lập. Giả sử chúng cùng nằm trong một tệp hoặc cấu trúc dự án thỏa quy tắc package/module của Java.

Diễn giải:

- `Notice` là **sealed root**.
- `TextNotice` và `Extension` là **hai direct permitted subtypes** của `Notice`.
- `record TextNotice` là **implicitly final**, nên không thể bị subclass.
- `Extension` là **non-sealed**, cho phép các lớp khác tự do `extends Extension` nếu quy tắc truy cập thông thường cho phép.
- Một lớp mới **không được tự ý `implements Notice` trực tiếp** nếu không nằm trong `Notice permits ...`.

Ví dụ sau **cố ý không biên dịch**:

~~~java
final class OtherNotice implements Notice {
    // ERROR: OtherNotice không là direct subtype được permits của Notice.
}
~~~

**Ý nghĩa của “đóng”:** compiler có thể biết **danh sách những kiểu trực tiếp** mà `Notice` cho phép, chứ không mặc định có danh sách đầy đủ mọi lớp ở mọi độ sâu trong cây kế thừa.

## 2. Ba cách tiếp tục một nhánh được phép

Một direct permitted subtype của sealed type phải có cách xác định tính mở rộng của nhánh:

| Dạng khai báo | Hậu duệ của nhánh | Ý nghĩa |
| --- | --- | --- |
| `final class End implements Root` | Không được subclass | Đóng tại đây |
| `record End(...) implements Root` | Record là implicitly final | Đóng tại đây |
| `sealed class Branch extends Root permits Child` | Chỉ những direct subtypes được `Branch` cho phép | Tiếp tục đóng theo tầng |
| `non-sealed class Extension extends Root` | Các lớp khác có thể subclass `Extension` theo quy tắc truy cập Java | **Mở lại nhánh** |
| `non-sealed interface Extension extends Root` | Các interface có thể extends và lớp có thể implements `Extension` theo quy tắc truy cập | **Mở lại nhánh interface** |

Ví dụ cây phân cấp:

~~~text
sealed Notice
├── final TextNotice                 (lá đóng)
└── non-sealed Extension            (nhánh mở)
    ├── PartnerExtension            (đã tồn tại)
    ├── FutureExtension             (mới được thêm)
    └── ...                          (còn có thể xuất hiện)
~~~

`Notice` vẫn chỉ cho **TextNotice** và **Extension** là direct subtypes. `PartnerExtension` và `FutureExtension` **không phải direct permitted subtypes của Notice**; chúng kế thừa `Notice` gián tiếp qua `Extension`.

**Điểm mấu chốt:** Một sealed root vẫn có **tập nhánh trực tiếp đóng**, nhưng khi một nhánh được khai báo `non-sealed`, sealed root **không còn kiểm soát tất cả các lớp con sâu hơn** của nhánh đó.

### Tại sao tên là `non-sealed` chứ không chỉ bỏ `sealed`?

Một lớp trực tiếp kế thừa sealed class/interface phải nói rõ cách nhánh tiếp tục được kiểm soát. Nếu là lớp thường, bạn phải dùng đúng một trong ba hướng `final`, `sealed` hoặc `non-sealed`; record vốn final theo ngôn ngữ.

Đoạn sau **cố ý không biên dịch**:

~~~java
sealed interface Root permits Open {
}

// ERROR: Open là direct permitted subtype nhưng không final/sealed/non-sealed.
class Open implements Root {
}
~~~

Sửa nếu muốn nhánh mở:

~~~java
non-sealed class Open implements Root {
}
~~~

Khi `Open` đã là `non-sealed`, một **lớp con bình thường** của nó không cần tiếp tục dùng từ khóa `non-sealed`:

~~~java
class PlugIn extends Open {
}
~~~

Thậm chí, dùng `non-sealed` cho lớp **chỉ** kế thừa một lớp `non-sealed` (mà không có sealed direct superclass/interface) sẽ là lỗi biên dịch:

~~~java
non-sealed class PlugIn extends Open { // ERROR: không có sealed direct supertype.
}
~~~

Đừng hiểu `non-sealed` là một annotation phải được ghi trên mọi hậu duệ; nó là một modifier tại **ranh giới giữa vùng sealed và vùng mở**.

## 3. `permits` quản lý quan hệ **trực tiếp**, không liệt kê mọi lớp cháu

Xét:

~~~java
sealed interface Notice permits TextNotice, Extension {
}

record TextNotice(String text) implements Notice {
}

non-sealed class Extension implements Notice {
}

final class PartnerExtension extends Extension {
}

final class FutureExtension extends Extension {
}
~~~

Các quan hệ hợp lệ:

- `TextNotice implements Notice`: trực tiếp và được permits.
- `Extension implements Notice`: trực tiếp và được permits.
- `PartnerExtension extends Extension`: gián tiếp trở thành `Notice`, không cần thêm tên vào `Notice permits`.
- `FutureExtension extends Extension`: cũng hợp lệ, kể cả khi được bổ sung sau này.

Các quan hệ không hợp lệ:

- `OtherNotice implements Notice` mà không nằm trong `permits`.
- `OtherNotice extends TextNotice`: record/final type không cho subclass.
- `non-sealed class Foo extends Extension` nếu `Foo` không có sealed direct supertype nào: modifier sai.

Nếu một sealed class có `sealed` subtype khác, nó có thể tiếp tục dùng `permits` để khống chế tầng tiếp theo. Tính mở/đóng được quyết định **từng nhánh**, không chỉ ở root.

### Giới hạn module và package

Direct permitted subtypes của một sealed type phải thỏa điều kiện đồng vị trí theo Java:

- Nếu sealed type nằm trong **named module**, các direct permitted subtypes phải ở **cùng module**.
- Nếu dùng **unnamed module**, chúng phải ở **cùng package**.

Đây là ràng buộc của **direct permitted subtypes**. Nó không tự động biến tất cả các hậu duệ của `non-sealed Extension` thành phần tử trong `permits`. Việc subclass một `non-sealed` class ở module/package khác vẫn phụ thuộc `public`, constructor accessibility, module exports và các quy tắc truy cập Java thông thường.

## 4. “Phá vỡ tính đóng” không có nghĩa root mất `sealed`

Hai nhận định cần phân biệt:

**Đúng:** `Notice` vẫn `sealed` và chỉ hai kiểu được liệt kê trong `permits` có quyền trực tiếp implement nó.

**Cũng đúng:** sau khi cho phép một subtype `non-sealed`, tổng số **kiểu concrete ở mọi tầng** có thể implement `Notice` là **không xác định trước**.

Ví dụ, thư viện ban đầu có:

~~~text
Notice
  TextNotice
  Extension
    PartnerExtension
~~~

Sau một bản nâng cấp, không đổi `Notice` hay `Extension`:

~~~text
Notice
  TextNotice
  Extension
    PartnerExtension
    FutureExtension
    ThirdPartyExtension
~~~

Khi lớp mới kế thừa `Extension`, nó **vẫn là một `Notice`** qua quan hệ kế thừa. Root không có quyền từ chối riêng lớp mới dựa trên `permits` của root, bởi lớp mới không trực tiếp implement root.

Đây chính là điểm **“non-sealed subtype phá vỡ tính đóng”**: không phá luật sealed của root, mà **mở lại một nhánh hậu duệ**, khiến hệ thống không thể lập danh sách chắc chắn tất cả *leaf/concrete subclasses* ở thời điểm thiết kế.

### Có thể “đóng lại” một nhánh con sau `non-sealed` không?

Có. Một lớp hậu duệ của `Extension` có thể tự được khai báo `final` hoặc `sealed` với những điều kiện hợp lệ của Java. Tuy nhiên, một nhánh con tự đóng **không làm cả `Extension` trở thành sealed trở lại**; người khác vẫn có thể khai báo một lớp con *khác* của `Extension` nếu accessibility cho phép.

Nói ngắn gọn: **`sealed` trên một hậu duệ tùy chọn không khôi phục tính đóng cho toàn bộ nhánh `non-sealed` bên trên**.

## 5. Tác động đến pattern matching for `switch` (Java 21)

Java 21 cho phép `switch` trên sealed type dùng **type patterns** và có thể được compiler chứng minh là **exhaustive** mà không cần `default`, nếu tập case **bao phủ toàn bộ những subtype được phép**.

Ví dụ:

~~~java
static String kind(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case Extension ext -> "extension";
    };
}
~~~

**Đây là switch expression exhaustive trong Java 21**, kể cả khi `Extension` là `non-sealed`.

**Tại sao?**

1. Mọi `Notice` không null đều thuộc một trong hai nhánh trực tiếp được `Notice` permits: `TextNotice` hoặc `Extension` (hoặc hậu duệ của chúng).
2. `case TextNotice text` match mọi instance của nhánh `TextNotice` (record final).
3. `case Extension ext` match **chính `Extension` và mọi subclass**, bao gồm những subclass tương lai mà sealed root không biết tên.
4. Vì vậy, **không cần `default`** để bao phủ các giá trị `Notice` không null.

**Phân biệt tuyệt đối hai mệnh đề:**

- “Một nhánh `non-sealed` có thể có **vô hạn kiểu con**”: đúng về khả năng mở rộng, không có danh sách con cố định.
- “Một switch trên sealed root **không thể exhaustive** nếu có nhánh `non-sealed`”: **sai**. Một type pattern cho **chính nhánh mở** có thể bao phủ tất cả các lớp con của nó.

Cách hiểu đúng của exhaustiveness ở đây là **type coverage**, không phải “phải liệt kê tên từng lớp concrete đang có”.

## 6. Sai lầm: chỉ liệt kê các hậu duệ hiện biết của nhánh mở

Giả sử đã có `PartnerExtension extends Extension`. Mã sau **cố ý không biên dịch**:

~~~java
static String broken(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        // ERROR: chưa bao phủ Extension và những subclass khác của nó.
    };
}
~~~

Compiler không thể dựa vào danh sách lớp `PartnerExtension` hiện biết để kết luận rằng **tất cả** `Extension` đều đã được xử lý. `Extension` có thể được khởi tạo trực tiếp (nếu không abstract), và các lớp khác có thể kế thừa nó. Kể cả `Extension` là `abstract non-sealed`, khả năng xuất hiện subclass mới vẫn khiến danh sách một vài subclass concrete **không** đủ để chứng minh exhaustive.

**Cách sửa đúng khi muốn xử lý partner riêng:**

~~~java
static String corrected(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        case Extension ext -> "another extension";
    };
}
~~~

- `case PartnerExtension` xử lý một subtype cụ thể đã biết.
- `case Extension` **bắt phần còn lại của cả nhánh mở**, gồm `Extension` và các subtype chưa được liệt kê.
- Compiler biết hai nhánh gốc `TextNotice`/`Extension` đã được bao phủ, nên switch expression exhaustive **không cần `default`**.

### Vì sao thứ tự case quan trọng?

Nếu đặt:

~~~java
case Extension ext -> "extension";
case PartnerExtension partner -> "partner"; // ERROR: dominated.
~~~

thì mọi `PartnerExtension` đã bị `case Extension` đứng trước nhận mất. Java 21 báo nhãn thứ hai bị **dominated**. Hãy đặt **subtype cụ thể trước**, **nhánh non-sealed tổng quát sau**.

Điều này liên quan trực tiếp đến bài **Sealed hierarchy**: khi nhánh mở được dùng trong pattern switch, đừng viết dàn case chỉ dựa vào các concrete class hiện có, và đừng đặt pattern bao phủ toàn nhánh quá sớm nếu còn muốn phân loại các subtype đặc biệt.

### Có nên dùng `default` để “chữa” lỗi thiếu nhánh?

Có thể thêm `default -> ...` để làm một switch exhaustive. Nhưng hãy cân nhắc ý nghĩa:

~~~java
static String permissive(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        default -> "other";
    };
}
~~~

Ở đây `default` bao phủ các đối tượng không null chưa match, nhưng nhãn `default` **không mang biến kiểu `Extension`**. Nếu tất cả những giá trị còn lại *theo hợp đồng domain* đúng là `Extension`, dùng `case Extension ext` thường rõ nghĩa hơn, có kiểu tĩnh chính xác và phản ánh rõ cấu trúc của sealed hierarchy.

Tuy nhiên, `default` là lựa chọn hợp lệ khi fallback chung chính là hành vi nghiệp vụ. Cái cần tránh là cho rằng có `default` đồng nghĩa bạn đã **hiểu và xử lý riêng** mọi subclass tương lai.

## 7. Mặt trái của exhaustive switch khi nhánh mở có thể phát triển

Giả sử hôm nay:

~~~java
return switch (notice) {
    case TextNotice t -> "text";
    case PartnerExtension p -> "partner";
    case Extension e -> "unknown extension";
};
~~~

Ngày mai một thư viện thêm:

~~~java
final class FutureExtension extends Extension {
}
~~~

Switch vẫn **biên dịch** khi client được biên dịch lại, vì `case Extension e` đã bao phủ mọi hậu duệ của `Extension`. Khi nhận `FutureExtension`, chương trình trả `"unknown extension"`.

Điều này vừa là **ưu điểm** vừa là **rủi ro**:

- **Ưu điểm:** API có điểm mở rộng không cần sửa từng consumer mỗi khi có plugin/subclass mới.
- **Rủi ro:** một subclass mới có ý nghĩa nghiệp vụ khác có thể âm thầm đi vào nhánh tổng quát. Compiler **không thể ép bạn viết nhánh riêng** cho mỗi hậu duệ tương lai của một `non-sealed` type.

Nếu domain yêu cầu **mọi biến thể phải được xử lý riêng**, bạn nên thiết kế tất cả nhánh là `final` hoặc `sealed` tiếp tục với `permits` — tức một cây phân cấp **đóng đến tận các lá cần phân biệt**.

Nếu domain là **plugin/extensibility**, nhánh `non-sealed` và một case tổng quát là thiết kế chủ ý. Khi đó việc xử lý plugin không biết trước cần **hợp đồng interface/abstract method** đủ rõ, thay vì chỉ dựa trên danh sách lớp ở thời điểm biên dịch.

### So sánh thiết kế

| Thiết kế | Điều gì có thể xuất hiện sau này? | Exhaustive switch thường viết thế nào? |
| --- | --- | --- |
| `sealed Root permits A,B`; `A`/`B` đều `final` | Không có thêm subclass của `A`/`B` | `case A`, `case B` |
| `sealed Root permits A,B`; `B` cũng `sealed`, chỉ cho phép `C,D` | Chỉ những descendant được phép trong từng tầng | Có thể bao phủ `A,C,D` hoặc bằng pattern tổng quát phù hợp |
| `sealed Root permits A,B`; `B` là `non-sealed` | Có thể xuất hiện subclass mới của `B` | `case A` và `case B` (bao phủ mọi subclass của B) |
| Chỉ có `case A` và vài subclass hiện biết của `B` | Vẫn có thể còn `B` hay subclass khác | **Không** exhaustive nếu không có nhánh bao phủ B/default |

**Thiết kế đúng không phải lúc nào cũng là “đóng hết”**. Mấu chốt là hợp đồng miền nghiệp vụ có cho phép người khác định nghĩa biến thể mới hay không.

## 8. Java 17: kiểm tra sealed/non-sealed; Java 21: kiểm tra exhaustive switch

`sealed` và `non-sealed` đã chính thức từ **Java 17**. Bạn có thể dùng `instanceof` ở Java 17 để phân nhánh theo type pattern; kiểm soát được subtype nào có thể implement trực tiếp sealed root.

~~~java
static String classify17(Notice notice) {
    if (notice instanceof TextNotice text) {
        return "text";
    }
    if (notice instanceof Extension extension) {
        return "extension";
    }
    throw new IllegalStateException("Unexpected Notice");
}
~~~

Đây là **phương thức minh họa** trong lớp có các kiểu được khai báo phù hợp, và khác với Java 21 pattern `switch`:

- `instanceof` kiểm tra theo từng điều kiện ở runtime.
- Compiler Java 17 **không kiểm tra tính exhaustive** của chuỗi `if` giống như một Java 21 pattern switch expression.
- Nhánh cuối có `throw` là quyết định của tác giả code, không phải bằng chứng compiler đã kiểm kê đủ mọi subtype.

**Java 21** mới cung cấp cú pháp chính thức:

~~~java
return switch (notice) {
    case TextNotice text -> "text";
    case Extension extension -> "extension";
};
~~~

Compiler Java 21 có thể chứng minh exhaustiveness theo cấu trúc sealed root và type coverage mà không cần `default`.

**Ghi chú phiên bản:** Pattern matching for `switch` ở các JDK 17–20 là preview với quy tắc/cú pháp thay đổi qua các lần preview. Đừng coi lệnh biên dịch Java 17 thông thường là đủ cho ví dụ pattern switch Java 21.

## 9. Chương trình chạy đầy đủ (Java 21)

Lưu tệp **`OpenBranchDemo.java`**:

~~~java
public class OpenBranchDemo {

    sealed interface Notice permits TextNotice, Extension {
    }

    // Record là implicitly final; đây là nhánh đóng.
    record TextNotice(String text) implements Notice {
    }

    // Nhánh mở: các lớp khác có thể extends Extension.
    static non-sealed class Extension implements Notice {
        private final String source;

        Extension(String source) {
            this.source = source;
        }

        String source() {
            return source;
        }
    }

    static final class PartnerExtension extends Extension {
        PartnerExtension(String source) {
            super(source);
        }
    }

    static final class FutureExtension extends Extension {
        FutureExtension(String source) {
            super(source);
        }
    }

    // Exhaustive không có default:
    // case Extension bao phủ cả subtype hiện tại và tương lai.
    static String classify(Notice notice) {
        return switch (notice) {
            case TextNotice text -> "text:" + text.text();
            case PartnerExtension partner ->
                    "partner:" + partner.source();
            case Extension extension ->
                    "extension:" + extension.source();
        };
    }

    static String broad(Notice notice) {
        return switch (notice) {
            case TextNotice text -> "text";
            case Extension extension -> "any extension";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new TextNotice("hello")));
        System.out.println(classify(new PartnerExtension("Acme")));
        System.out.println(classify(new Extension("legacy")));
        System.out.println(classify(new FutureExtension("future")));
        System.out.println(broad(new FutureExtension("future")));

        try {
            classify(null);
        } catch (NullPointerException ex) {
            System.out.println("null:NPE");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 trở lên**:

~~~bash
javac --release 21 OpenBranchDemo.java
java OpenBranchDemo
~~~

**Stdout chính xác:**

~~~text
text:hello
partner:Acme
extension:legacy
extension:future
any extension
null:NPE
~~~

Diễn giải:

1. `TextNotice("hello")` match direct permitted record branch ⇒ `text:hello`.
2. `PartnerExtension` match case cụ thể đứng trước case tổng quát ⇒ `partner:Acme`.
3. Instance `Extension` tự nó match `case Extension` ⇒ `extension:legacy`.
4. `FutureExtension` không có tên trong `permits` của root và không có case riêng, nhưng **vẫn match `case Extension`** ⇒ `extension:future`.
5. Hàm `broad` có đúng hai case tương ứng hai direct permitted branches, nên exhaustive. Một subclass của `Extension` trả `any extension`.
6. `null` không match type pattern `TextNotice`/`Extension`; khi không có `case null`, switch ném `NullPointerException`. Đoạn `catch` trong main chỉ chuyển ngoại lệ thành dòng stdout đã ghi.

**Điểm nổi bật:** Root chỉ có **hai direct permitted subtypes**, nhưng ứng dụng có thể có nhiều **concrete subtypes** hơn hai; mọi subtype bên dưới nhánh non-sealed đã được xử lý ở `case Extension`.

## 10. Những chương trình bị compiler từ chối — và lý do chính xác

### Lỗi A. Không bao phủ nhánh non-sealed

Đoạn sau **cố ý không biên dịch**, đặt trong lớp có khai báo `Notice`, `TextNotice` và `PartnerExtension`:

~~~java
static String broken(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        // ERROR: còn Extension và các subclass khác.
    };
}
~~~

Thông báo của Java 21 thường có dạng:

~~~text
the switch expression does not cover all possible input values
~~~

**Cách sửa:** thêm `case Extension extension -> ...` (sau `case PartnerExtension`) hoặc một `default` có chủ đích.

### Lỗi B. Nhánh tổng quát che nhánh cụ thể

~~~java
static String badOrder(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case Extension extension -> "all extensions";
        case PartnerExtension partner -> "partner"; // ERROR: dominated.
    };
}
~~~

Mọi `PartnerExtension` đều là `Extension`. Compiler từ chối nhánh sau bị che hoàn toàn.

### Lỗi C. Lớp trực tiếp implement root nhưng không được permits

~~~java
final class Unauthorized implements Notice {
    // ERROR: không được Notice cho phép trực tiếp.
}
~~~

**Cách sửa:** nếu thật sự muốn thêm một direct variant, người sở hữu `Notice` phải sửa `permits` và kiểm tra các switch exhaustive liên quan. Nếu mục tiêu là plugin, kế thừa `Extension` thay vì implement sealed root trực tiếp.

### Lỗi D. Thiếu modifier trên direct permitted subtype

~~~java
sealed interface Root permits Open { }

class Open implements Root { // ERROR.
}
~~~

**Sửa:** `final class Open`, `sealed class Open permits ...`, hoặc `non-sealed class Open` tùy ý đồ thiết kế.

### Lỗi E. Dùng `non-sealed` ở nơi không có sealed direct supertype

~~~java
non-sealed class Child extends Extension { // ERROR nếu Extension là direct non-sealed.
}
~~~

**Sửa:** thường chỉ cần `class Child extends Extension` hoặc `final class Child extends Extension`. Nếu muốn child tiếp tục thiết lập một hierarchy đóng mới, có thể cân nhắc khai báo child là `sealed` với `permits` theo các quy tắc Java.

### Lỗi F. Tưởng `default` hoặc null là hằng hợp lệ của sealed root

~~~java
return switch (notice) {
    case TextNotice text -> "text";
    case Extension extension -> "extension";
};
~~~

Code trên exhaustive cho **giá trị không null**. `null` vẫn có thể ném `NullPointerException`. Nếu hợp đồng cần xử lý null, có thể viết:

~~~java
return switch (notice) {
    case null -> "missing";
    case TextNotice text -> "text";
    case Extension extension -> "extension";
};
~~~

`case null` là nhãn riêng, không phải một subtype mới trong `permits`.

## 11. Reflection không thể liệt kê tất cả hậu duệ của nhánh mở

Java cung cấp introspection cho sealed type:

~~~java
System.out.println(Notice.class.isSealed()); // true

Class<?>[] directTypes = Notice.class.getPermittedSubclasses();
System.out.println(directTypes.length);       // 2
~~~

Đây là đoạn minh họa trong ngữ cảnh lớp `OpenBranchDemo` có hai direct permitted types của `Notice`. `getPermittedSubclasses()` phản ánh **direct permitted subclasses/subinterfaces của sealed type**, không phải tự động tìm mọi lớp con gián tiếp.

Với `Extension` là `non-sealed`:

~~~java
System.out.println(Extension.class.isSealed()); // false
System.out.println(
        Extension.class.getPermittedSubclasses() == null
); // true — type không sealed.
~~~

Đừng dùng `Notice.class.getPermittedSubclasses()` như một “registry” chắc chắn liệt kê mọi plugin/concrete leaf: `PartnerExtension` và `FutureExtension` không phải direct permitted subtypes của root, nên không nằm trong danh sách trực tiếp.

Nếu hệ thống plugin cần khám phá tất cả implementation thực sự khả dụng, hãy dùng cơ chế đăng ký/khám phá phù hợp với kiến trúc (chẳng hạn `ServiceLoader` trong tình huống phù hợp) thay vì suy luận chỉ từ `permits`. Đây là một bài toán quản lý plugin, **khác** với quy tắc sealed của Java.

## 12. Những nhầm lẫn thường gặp

| Nhận định | Đúng/sai | Giải thích |
| --- | --- | --- |
| “Root có `sealed` thì không thể thêm bất kỳ subclass nào ở mọi tầng.” | **Sai** | `non-sealed` branch cho phép thêm subclass gián tiếp |
| “`non-sealed` vô hiệu hóa `permits` của root.” | **Sai** | Root vẫn giới hạn direct subtypes |
| “Subclass của `non-sealed` phải được thêm vào `permits` của root.” | **Sai** | Nó không trực tiếp extends/implements root |
| “Cứ có nhánh `non-sealed` thì `switch` không thể exhaustive.” | **Sai** | `case Extension` bao phủ cả nhánh mở |
| “Liệt kê tất cả concrete subclasses hiện thấy là đủ.” | **Sai** | Branch vẫn mở cho subclasses tương lai và có thể instantiable |
| “`case PartnerExtension` đứng sau `case Extension` là ổn.” | **Sai** | Bị dominance vì kiểu con đã được nhánh cha bắt |
| “Một switch exhaustive có nghĩa compiler sẽ nhắc xử lý mọi plugin tương lai.” | **Sai** | Pattern nhánh mở có thể nhận plugin mới mà không cần case riêng |
| “`non-sealed` phải ghi trên mọi lớp hậu duệ.” | **Sai** | Modifier này chỉ hợp lệ nếu có sealed direct supertype tương ứng |
| “Mọi direct subtype của sealed type đều phải là `final`.” | **Sai** | Có thể `sealed` tiếp hoặc `non-sealed`; record là implicitly final |
| “Reflection `getPermittedSubclasses` liệt kê cả cháu của non-sealed type.” | **Sai** | Nó chỉ cho danh sách direct permitted types |
| “`default` tự xử lý `null` trong pattern switch.” | **Sai** | Java 21 cần `case null` nếu muốn xử lý null trực tiếp |

### Một mô hình tư duy đúng

Hãy tách **hai phép hỏi**:

1. “Những kiểu nào được phép **trực tiếp** ở dưới root?” — `permits` trả lời.
2. “Những đối tượng runtime nào có thể thuộc **toàn bộ cây con** của từng nhánh?” — `final`, `sealed` và `non-sealed` quyết định.

Nếu nhánh là `non-sealed`, câu trả lời thứ hai là **mở**, dù câu trả lời thứ nhất vẫn cố định. Một type pattern cho **nhánh gốc được phép** vẫn có thể bao phủ toàn bộ cây con đó.

## 13. Bài tập thực hành

**Câu 1.** Giả sử:

~~~java
sealed interface Shape permits Circle, Polygon { }
record Circle(double radius) implements Shape { }
non-sealed class Polygon implements Shape { }
final class Triangle extends Polygon { }
~~~

Các direct permitted subtypes của `Shape` là gì? `Triangle` có cần nằm trong `permits` không?

**Câu 2.** Có thể viết thêm `final class Rectangle extends Polygon` mà không sửa `Shape` không? Vì sao?

**Câu 3.** Xét `switch (shape)` trên selector có kiểu tĩnh `Shape`:

~~~java
return switch (shape) {
    case Circle c -> "circle";
    case Triangle t -> "triangle";
};
~~~

Java 21 có xem switch expression này exhaustive không? Nên thêm nhánh nào?

**Câu 4.** Nếu thêm `case Polygon p -> "polygon";` **trước** `case Triangle t`, compiler chấp nhận không? Cách sửa?

**Câu 5.** Với:

~~~java
return switch (shape) {
    case Circle c -> "circle";
    case Triangle t -> "triangle";
    case Polygon p -> "polygon";
};
~~~

Sau khi thêm `Rectangle extends Polygon`, cần sửa switch để Java 21 coi exhaustive không? `Rectangle` vào nhánh nào?

**Câu 6.** Viết hai cách giải quyết rủi ro bỏ sót subtype mới: một cách dành cho domain **đóng**, một cách dành cho **plugin/open extension**.

**Câu 7.** Vì sao `final class Extra implements Shape` không hợp lệ nếu `Shape` chỉ permits `Circle` và `Polygon`, trong khi `final class Extra extends Polygon` lại hợp lệ?

**Câu 8.** Một class trực tiếp được permits nhưng không có modifier `final`, `sealed` hoặc `non-sealed` (và không là record). Compiler sẽ làm gì?

**Câu 9.** Sau khi `Polygon` là `non-sealed`, có thể khai báo `non-sealed class Triangle extends Polygon` không nếu `Triangle` không có sealed direct supertype nào khác?

**Câu 10.** `Shape.class.getPermittedSubclasses()` cho biết gì? Có đủ để liệt kê tất cả subclass/plugin của `Polygon` không?

**Câu 11.** `case Polygon p` có match `null` không? Nếu muốn trả `"missing"` cho null, thêm gì?

**Câu 12.** Tại sao câu “compiler exhaustive nghĩa là mọi concrete subtype ở mọi tầng đều được xử lý riêng” là sai trong cây sealed chứa một nhánh `non-sealed`?

### Đáp án tham khảo

1. **`Circle` và `Polygon`**. `Triangle` không cần trong `permits` vì nó kế thừa `Shape` gián tiếp qua `Polygon`.
2. **Có**, nếu các quy tắc visibility/constructor/module thông thường cho phép. `Polygon` là `non-sealed`.
3. **Không**. Còn `Polygon` và các subclass khác. Thêm `case Polygon p -> ...` ở sau nhánh `Triangle` hoặc `default` có chủ đích.
4. **Không**: `Triangle` bị dominated bởi `Polygon`. Đặt `Triangle` trước `Polygon`.
5. **Vẫn exhaustive**. `Rectangle` sẽ vào `case Polygon p`.
6. Domain đóng: dùng các nhánh `final` hoặc `sealed` tiếp với `permits` để compiler có cây kiểu hữu hạn. Domain plugin: chủ ý dùng `non-sealed`, định nghĩa API chung và nhánh `case Polygon p`/xử lý fallback có hợp đồng.
7. `Extra implements Shape` là direct subtype không permits ⇒ lỗi. `Extra extends Polygon` đi qua nhánh mở ⇒ hợp lệ.
8. **Lỗi biên dịch**: direct permitted subtype phải chỉ rõ chiến lược tiếp tục kế thừa, trừ trường hợp như record implicitly final.
9. **Không**: modifier `non-sealed` cần sealed direct supertype, không đơn thuần là có sealed ancestor xa hơn.
10. Danh sách **direct permitted types** của `Shape`, không liệt kê mọi descendant của `Polygon`.
11. **Không**. Thêm `case null -> "missing"` khi null là giá trị đầu vào được chấp nhận.
12. Vì `case Polygon p` khớp mọi subtype hiện có và tương lai của `Polygon`, giúp switch exhaustive về **type coverage**, nhưng không phân loại riêng từng concrete subtype.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Sealed Classes](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html): `permits`, quy tắc `final`/`sealed`/`non-sealed`, vị trí module/package.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục tiêu thiết kế sealed class/interface, nhánh mở bằng `non-sealed`.
- [JLS 21 — `8.1.1.2 Sealed, Non-sealed, and Final Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): điều kiện khai báo và quan hệ kế thừa.
- [JLS 21 — `9.1.1.4 Sealed and Non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4): mở/đóng nhánh interface.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): type coverage, dominance và exhaustive switch với sealed selector.
- [JLS 21 — `14.11.1.1 Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): quy tắc compiler chứng minh tính đầy đủ.
- [JLS 21 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression và xử lý runtime.
- [Java SE 21 API — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isSealed()` và `getPermittedSubclasses()`.
