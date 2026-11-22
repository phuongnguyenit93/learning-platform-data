# Dùng -Xlint để phát hiện nhóm cảnh báo có ý nghĩa

**`javac -Xlint` là công cụ chẩn đoán tĩnh của trình biên dịch Java.** Nó phát hiện những biểu hiện đáng nghi hoặc hành vi có thể không như mong đợi **ngay lúc biên dịch**, trước khi chương trình được chạy. Đặc biệt hữu ích là các nhóm cảnh báo liên quan đến generics không an toàn (`rawtypes`, `unchecked`), sử dụng API cũ (`deprecation`, `removal`), dòng điều khiển khó nhận ra (`fallthrough`), hợp đồng serialization (`serial`), resource (`try`), override và một số hành vi liên quan tới module.

Bài học tập trung vào cách **chọn và đọc nhóm cảnh báo có ý nghĩa**, tạo ví dụ tái hiện, sửa nguyên nhân, phân biệt cảnh báo với lỗi, cấu hình mức nghiêm ngặt và áp dụng trong CI. Các ví dụ chạy trên Java 17+, dùng `javac` của JDK 21 để đối chiếu kết quả khi biên soạn.

## 1. Warning của javac khác error ở điểm nào?

- **Error:** lỗi về cú pháp, kiểu, quyền truy cập hoặc quy tắc ngôn ngữ làm đơn vị biên dịch không hợp lệ. Một build có error không thành công.
- **Warning:** một trường hợp compiler *vẫn có thể chấp nhận*, nhưng đáng để người phát triển xem xét. Ví dụ, code dùng raw `List` vẫn hợp lệ vì tương thích với Java cũ, song có thể vượt qua kiểm tra generics và gây `ClassCastException` khi chạy.
- **Note:** thông tin tóm tắt hoặc chỉ dẫn khác với warning chi tiết, chẳng hạn “Recompile with -Xlint:unchecked for details”. Một note không nhất thiết là warning đầy đủ và không nói rõ vị trí nguyên nhân cho đến khi bật loại lint phù hợp.

Đừng hiểu **“biên dịch thành công” là “không có cảnh báo”**, hoặc **“không có cảnh báo” là “chương trình đúng”**. `javac` không thay thế unit test, runtime instrumentation, static analyzers khác hay kiểm thử bảo mật.

Ví dụ đoạn mã có thể biên dịch nhưng bị cảnh báo:

```java
java.util.List raw = new java.util.ArrayList<String>();
raw.add("hello");
```

Với `-Xlint:rawtypes,unchecked`, `javac` báo về raw type `List` và lời gọi `add` không được kiểm tra đầy đủ theo generics. Nó không tự sửa code hoặc chứng minh lúc chạy chắc chắn lỗi. Lợi ích là cảnh báo một thiết kế có rủi ro để ta xem xét.

## 2. Các cú pháp -Xlint quan trọng

```bash
javac -Xlint -d out Example.java
javac -Xlint:all -d out Example.java
javac -Xlint:rawtypes,unchecked -d out Example.java
javac -Xlint:deprecation,removal -d out Example.java
javac -Xlint:all,-serial -d out Example.java
javac -Xlint:none -d out Example.java
```

Đây là những **mẫu lệnh**; `Example.java` phải là một file Java thật thì mới chạy được.

| Cú pháp | Ý nghĩa |
| --- | --- |
| `-Xlint` | Bật tập nhóm warning được `javac` đánh dấu là khuyến nghị cho phiên bản JDK hiện tại |
| `-Xlint:all` | Bật toàn bộ các nhóm lint được hỗ trợ |
| `-Xlint:rawtypes,unchecked` | Chỉ định các nhóm muốn bật trong một đối số |
| `-Xlint:all,-serial` | Bật các nhóm rồi loại trừ nhóm `serial`; dấu trừ bên trong danh sách dùng để loại trừ một key |
| `-Xlint:none` | Vô hiệu hóa các nhóm cảnh báo thuộc hệ thống lint; không nên coi là nút tắt mọi diagnostic |
| `-Werror` | Yêu cầu coi việc có warning là thất bại của compilation; có thể kết hợp `-Xlint` |
| `-Xmaxwarns 10` | Giới hạn số warning chi tiết được hiển thị; không sửa code và không loại bỏ bản chất warning |

Để tìm các key **thực sự được bản `javac` hiện tại hỗ trợ**, dùng:

```bash
javac --help-lint
javac -X
javac --help
javac -version
```

`--help-lint` đặc biệt hữu ích vì danh sách nhóm có thể **thay đổi qua các bản JDK**. Đừng sao chép một key chỉ tồn tại ở JDK mới hơn vào compiler cũ rồi cho rằng lỗi “invalid flag” là lỗi mã Java. Ví dụ `-Xlint:all,-serial` dùng dấu phẩy trong **cùng một đối số**; không thêm khoảng trắng để biến `-serial` thành tùy chọn riêng.

**Chú ý:** `-Xlint` và `-Xlint:all` có phạm vi khuyến nghị phụ thuộc tài liệu phiên bản. Một số cảnh báo có thể đã bật mặc định, trong khi các nhóm khác chỉ được hiển thị chi tiết khi yêu cầu. Muốn tái hiện chính xác, luôn ghi nhận `javac -version` và các flag đã truyền.

## 3. Chọn nhóm lint theo rủi ro thực tế

| Nhóm | Điều cần phát hiện | Vì sao có ý nghĩa |
| --- | --- | --- |
| `rawtypes` | Sử dụng generic class/interface mà bỏ tham số kiểu, như `List` thay vì `List<String>` | Mất kiểm tra kiểu, thường là dấu hiệu code legacy cần cải thiện |
| `unchecked` | Gán/ép kiểu hoặc lời gọi có kiểm tra generic không đầy đủ | Có thể để lọt type mismatch tới runtime |
| `deprecation` | Sử dụng API đã bị đánh dấu deprecated thông thường | Cần kiểm tra cách thay thế và thời hạn chuyển đổi |
| `removal` | Sử dụng API deprecated **được đánh dấu for removal** | Rủi ro tương thích JDK cao hơn, nên ưu tiên xử lý |
| `fallthrough` | Nhánh `switch` kiểu colon rơi xuống nhánh kế tiếp không có `break` | Có thể làm chạy thêm logic ngoài ý muốn |
| `serial` | Ví dụ: class `Serializable` hoặc ngoại lệ thiếu `serialVersionUID` | Có thể gây bất ngờ về hợp đồng serialization |
| `try` | Những vấn đề liên quan đến `try`/try-with-resources | Trợ giúp quản lý resource và tránh lỗi code dễ bỏ sót |
| `cast` | Một số phép cast không cần thiết | Giảm nhiễu, tránh code khó hiểu |
| `overrides`, `overloads` | Một số tình huống đáng nghi về override/overload | Giúp tìm API khó hiểu hoặc sai dự định |
| `static` | Truy cập thành viên static thông qua một instance | Làm rõ ý nghĩa truy cập theo class |
| `path`, `options` | Vấn đề về đường dẫn và tùy chọn biên dịch | Có thể phát hiện build cấu hình sai |
| `module`, `exports` | Các vấn đề liên quan hệ thống module | Có giá trị với dự án JPMS |
| `processing` | Vấn đề trong quá trình annotation processing | Có ích với annotation processor |
| `varargs` | Một số khai báo/lời gọi varargs không an toàn | Hữu ích khi trộn generic với mảng |
| `this-escape` | Rò rỉ `this` trước khi khởi tạo subclass hoàn tất ở JDK hỗ trợ | Phát hiện một số tình huống object chưa được xây dựng đầy đủ |

**Danh sách là ví dụ có chủ đích, không phải bảng đầy đủ của tất cả JDK.** Những key mới như `this-escape` có thể không có trên JDK 17; hãy kiểm tra `javac --help-lint`. Các nhóm như `removal` có thể được bật mặc định. Không phải một warning thuộc nhóm trên luôn có nghĩa sẽ gây lỗi runtime; cần đọc hoàn cảnh code và hợp đồng API.

### Thứ tự triage gợi ý

1. **Nguy cơ sai hành vi/runtime:** `unchecked`, `fallthrough`, `varargs` và vấn đề mất an toàn kiểu thực sự.
2. **Rủi ro tương thích/nâng cấp:** `removal`, `deprecation`, `serial`, `module`.
3. **Chất lượng code dễ kiểm tra:** `rawtypes`, `cast`, `static`, `overrides`.
4. **Cấu hình build:** `path`, `options` và `processing` khi môi trường phù hợp.

Thứ tự trên là một **cách đánh giá dựa trên tác động**, không phải cấp độ nguy hiểm do JLS quy định. Ví dụ một `fallthrough` có chủ đích có thể hợp lệ; một warning `path` phát hiện dependency bị thiếu lại có thể quan trọng hơn nhiều.

## 4. Bài thực hành: phát hiện năm nhóm cảnh báo trong một chương trình

Tạo file duy nhất `LintLab.java`:

```java
import java.util.ArrayList;
import java.util.List;

class LegacyApi {
    @Deprecated(since = "17")
    static String oldName() { return "old"; }
}

class DataProblem extends Exception { }

public class LintLab {
    public static void main(String[] args) {
        List raw = new ArrayList<String>();
        raw.add("one");
        List<String> names = raw;
        System.out.println(names.get(0));
        System.out.println(LegacyApi.oldName());

        int mode = 1;
        switch (mode) {
            case 1:
                System.out.println("one");
            case 2:
                System.out.println("two");
                break;
            default:
                System.out.println("other");
        }
    }
}
```

Tất cả class không `public` đều nằm cùng file với `public class LintLab`, nên file này hợp lệ trên Java 17+. `DataProblem extends Exception` là class có thể serialize theo cơ chế `Throwable` nhưng không khai báo `serialVersionUID`; điều này phục vụ ví dụ cảnh báo `serial`.

Chạy trong thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -d out LintLab.java
java -cp out LintLab
```

Với JDK 21 đã kiểm chứng, lệnh biên dịch báo **6 warning**: một `serial`, một `rawtypes`, hai `unchecked`, một `deprecation`, một `fallthrough`. Phần đầu và cuối của cảnh báo, viết lại dưới dạng **trích yếu**, là:

```text
warning: [serial] serializable class DataProblem has no definition of serialVersionUID
warning: [rawtypes] found raw type: List
warning: [unchecked] unchecked call to add(E) as a member of the raw type List
warning: [unchecked] unchecked conversion
warning: [deprecation] oldName() in LegacyApi has been deprecated
warning: [fallthrough] possible fall-through into case
6 warnings
```

Đây là những **dòng rút gọn** từ diagnostic; `javac` thực tế còn in đường dẫn, số dòng, vị trí `^` và chi tiết type variable. Nội dung và số dòng có thể khác trên các bản JDK.

Điều quan trọng: **quá trình biên dịch vẫn thành công** vì những lỗi trong ví dụ được phân loại là warning, trừ khi dùng chế độ coi warning là lỗi. Chạy chương trình cho stdout **chính xác**:

```text
one
old
one
two
```

Hai dòng `one`/`two` cuối cho thấy điều đáng ngờ của `fallthrough`: `case 1` chạy rồi tiếp tục sang `case 2`. Nếu đó là chủ đích, cần viết rõ để người đọc biết; nếu không, sửa cấu trúc `switch` để tránh tác dụng phụ.

### Đọc từng warning ở đúng vị trí

| Vị trí trong chương trình | Warning | Nguyên nhân | Hướng sửa |
| --- | --- | --- | --- |
| `class DataProblem extends Exception` | `[serial]` | Có khả năng serialize nhưng không có `serialVersionUID` | Khai báo UID theo hợp đồng serialization |
| `List raw = ...` | `[rawtypes]` | Dùng kiểu generic thô, bỏ tham số kiểu | `List<String>` |
| `raw.add("one")` | `[unchecked]` | Gọi `add` qua raw type, bỏ kiểm tra kiểu generic | Định kiểu collection tại khai báo |
| `List<String> names = raw` | `[unchecked]` | Gán raw List sang generic List một cách unchecked | Tránh raw type, hoặc kiểm tra phần tử ở ranh giới dữ liệu cũ |
| `LegacyApi.oldName()` | `[deprecation]` | Gọi API được đánh dấu deprecated | Tìm API thay thế dựa trên tài liệu |
| `case 2:` sau `case 1` | `[fallthrough]` | Không có `break` giữa hai nhánh | Sửa luồng điều khiển nếu không chủ đích |

Đây là **bản đồ từ warning đến quyết định sửa mã**, không phải lời khuyên xóa mọi warning bằng suppression. Ví dụ dùng raw collection có thể nằm trong thư viện đời cũ không kiểm soát được; khi đó cần vùng adapter/cast có kiểm tra dữ liệu thay vì thay đổi toàn bộ API một cách thiếu kiểm soát.

## 5. Bản sửa: biên dịch sạch với -Werror

Tạo file riêng `LintClean.java`:

```java
import java.util.ArrayList;
import java.util.List;

class CurrentApi {
    static String name() { return "new"; }
}

class DataIssue extends Exception {
    private static final long serialVersionUID = 1L;
}

public class LintClean {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("one");
        System.out.println(names.get(0));
        System.out.println(CurrentApi.name());

        int mode = 1;
        switch (mode) {
            case 1 -> {
                System.out.println("one");
                System.out.println("two");
            }
            case 2 -> System.out.println("two");
            default -> System.out.println("other");
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -Werror -d out LintClean.java
java -cp out LintClean
```

Đã kiểm chứng trên JDK 21 với `--release 17`: lệnh `javac` kết thúc thành công, không phát ra các warning trên. Stdout của lệnh `java`:

```text
one
new
one
two
```

Điều gì đã thay đổi?

1. `List<String>` thay raw `List`, nên `add` và phép gán generic được compiler kiểm tra.
2. Thay API deprecated bằng `CurrentApi.name()` chỉ để minh họa hướng đi. Với code thật, phải xác định API thay thế **tương đương về ngữ nghĩa**, không tự đoán tên mới.
3. `DataIssue` khai báo `serialVersionUID` nhằm làm rõ phiên bản serialization. Giá trị UID phải phù hợp với hợp đồng tương thích của class thực tế.
4. Dùng **switch rule `->` của Java 17**, trong đó case 1 in cả `one` và `two` để giữ nguyên hành vi rơi qua của ví dụ cũ một cách **tường minh**. Kết quả runtime cố ý đổi `old` thành `new` do đổi API minh họa.
5. `-Werror` yêu cầu build không chấp nhận warning, hữu ích khi nhóm lint đã được nhóm phát triển thống nhất và baseline đủ sạch.

**Không được lấy việc “hết warning” làm bằng chứng đã sửa đúng chức năng.** Sau chỉnh sửa phải chạy test kiểm chứng business behavior: ví dụ ở đây cố ý giữ cả hai dòng output của `case 1`, nhưng trong ứng dụng khác có thể mong đợi duy nhất `one`.

## 6. Generics: rawtypes và unchecked khác nhau thế nào?

Đây là hai warning liên quan chặt, nhưng khác góc nhìn:

- **`rawtypes`** nhắc về **cách khai báo/sử dụng một generic type thiếu type arguments**: `List`, `Map`, `Class` thay vì `List<String>`, `Map<K,V>`, `Class<?>`.
- **`unchecked`** nhắc về **phép toán mà compiler không thể kiểm tra an toàn kiểu generic đầy đủ**, như unchecked assignment, cast hoặc lời gọi qua raw generic.

Ví dụ:

```java
List raw = new ArrayList<String>();   // rawtypes
raw.add(123);                         // unchecked call
List<String> strings = raw;           // unchecked conversion
// String first = strings.get(0);     // Có thể ClassCastException runtime
```

Mã trên là **đoạn minh họa** đặt trong một method và có import `java.util.List`, `java.util.ArrayList`; không phải file Java độc lập. Dù `ArrayList<String>` đã có tham số kiểu ở initializer, biến `raw` vẫn được khai báo raw và làm mất bảo đảm kiểu tại những lời gọi dùng biến đó.

Cách sửa khi **đã biết rõ loại phần tử**:

```java
List<String> strings = new ArrayList<>();
strings.add("ok");
// strings.add(123); // LỖI compile-time: Integer không phù hợp String.
```

Nếu dữ liệu đến từ API legacy trả `List`, không nên ép kiểu bừa để giấu warning. Có thể xử lý ở **ranh giới**:

```java
static List<String> validatedStrings(List<?> values) {
    List<String> result = new ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String s)) {
            throw new IllegalArgumentException("Not a String: " + value);
        }
        result.add(s);
    }
    return result;
}
```

Đây là **method minh họa**, cần đặt trong class có import `java.util.List`, `java.util.ArrayList`. Nó chủ động kiểm tra từng phần tử rồi tạo List kiểu `String`, thay vì chỉ cast unchecked và giả định toàn bộ collection hợp lệ. Với dữ liệu lớn, việc sao chép và kiểm tra có chi phí; cân nhắc hợp đồng API và đường dữ liệu thực tế.

### Vì sao warning unchecked quan trọng?

Do type erasure, không thể kiểm tra mọi generic parameter của object ở runtime như kiểu primitive. Phép cast `(List<String>) someObject` có thể chỉ kiểm tra object thuộc raw `List`; từng phần tử có đúng `String` hay không vẫn chưa được bảo đảm. Vì thế warning cần được điều tra, nhất là ở API công cộng hoặc chỗ nhập dữ liệu không đáng tin.

## 7. Deprecated và forRemoval: ưu tiên khác nhau

Hai nhóm thường gặp:

```java
@Deprecated(since = "17")
public static void oldMethod() {}

@Deprecated(since = "17", forRemoval = true)
public static void obsoleteMethod() {}
```

Đây là ví dụ khai báo trong một class; không phải chương trình độc lập. `@Deprecated` thông thường có ý nghĩa nên tránh dùng mới hoặc lên kế hoạch thay. Với `forRemoval = true`, API được thông báo **dự định loại bỏ trong tương lai** theo lộ trình thư viện; compiler phân biệt warning `removal` với `deprecation` thông thường.

Chọn các flag:

```bash
javac -Xlint:deprecation,removal -d out App.java
```

`App.java` cần là file nguồn thực có sử dụng API tương ứng. `-deprecation` cũng là cách yêu cầu compiler cho chi tiết deprecated use và được tài liệu `javac` mô tả tương đương `-Xlint:deprecation`.

Một số JDK hiển thị warning `removal` ngay cả khi bạn không viết `-Xlint:removal` vì nhóm này có thể được bật mặc định. Vì vậy dùng `-Xlint:all` hoặc bật các nhóm quan trọng **không phải lúc nào cũng làm tăng tổng số cảnh báo so với mặc định**.

Khi xử lý:

- Kiểm tra thư viện/JDK và phiên bản sử dụng, Javadoc hoặc migration guide.
- Xác định API thay thế có hợp đồng tương đương về dữ liệu, exception, thread-safety và hiệu năng không.
- Ưu tiên `removal` khi nâng JDK để tránh ứng dụng ngừng biên dịch/chạy sau một lần nâng.
- Ghi rõ lý do nếu buộc giữ lời gọi legacy trong một vùng nhỏ và có kế hoạch loại bỏ.

Không coi `@Deprecated` là một lỗi tự động. Nó là tín hiệu bảo trì, mức ưu tiên tùy phạm vi sử dụng và thời điểm module đổi phiên bản.

## 8. Fallthrough: phân biệt lỗi logic và ý định

Switch dùng dấu hai chấm kiểu truyền thống **có thể rơi xuống case sau** nếu không `break`, `return` hoặc đường thoát phù hợp:

```java
switch (status) {
    case 1:
        log("started");
    case 2:
        log("stopped");
        break;
    default:
        log("unknown");
}
```

Đây là **đoạn minh họa**, trong đó `status` và `log` phải được định nghĩa bởi ngữ cảnh. Nếu `status == 1`, cả `started` và `stopped` được ghi: đó có thể là bug.

`-Xlint:fallthrough` giúp phát hiện cấu trúc đáng ngờ. Tùy yêu cầu, hãy:

- **Thêm `break`** nếu mỗi nhánh phải chạy độc lập.
- **Dùng switch rule `->`** (Java 17+) để tránh fallthrough ngầm, thể hiện rõ nhánh nào thực hiện logic gì.
- **Giữ fallthrough có chủ đích** khi được thiết kế và kiểm tra kỹ. Việc thêm comment là tài liệu ý định, nhưng không nên giả định mọi compiler tự nhận comment thành cơ chế suppression chính thức.

Ví dụ sửa logic để mỗi case xử lý độc lập:

```java
switch (status) {
    case 1 -> log("started");
    case 2 -> log("stopped");
    default -> log("unknown");
}
```

Đừng máy móc thêm `break` nếu ứng dụng phụ thuộc vào việc chạy cả hai tác vụ. Cần kiểm tra hành vi trước và sau theo yêu cầu nghiệp vụ.

## 9. Serial: hiểu về serialVersionUID

Một class `Serializable` hoặc class kế thừa từ kiểu serializable như `Exception` có thể nhận warning `serial` khi không khai báo `serialVersionUID`. Serialization framework của Java dùng số này để nhận diện tính tương thích giữa dữ liệu được serialize và định nghĩa class được nạp khi deserialization. Một UID không đúng hoặc không tương thích có thể gây `InvalidClassException`.

Ví dụ:

```java
class DomainException extends Exception {
    private static final long serialVersionUID = 1L;

    DomainException(String message) {
        super(message);
    }
}
```

Đây là class Java hoàn chỉnh nhưng không có `main`; có thể đặt trong file `DomainException.java` hoặc dùng trong project.

**Không phải mọi lớp đều cần serialVersionUID.** Chỉ những class tham gia cơ chế Java serialization mới liên quan tới nhóm cảnh báo này. Với DTO trong JSON, protocol buffers hoặc dữ liệu DB, phải xem giao thức serialize thực sự sử dụng; đừng thêm `implements Serializable` chỉ để làm “chuẩn”.

Cũng không chọn UID tùy ý cho class đã có dữ liệu serialized đang được lưu trữ và cần tương thích với binary cũ. Cần xem versioning/compatibility contract.

## 10. Varargs và generic array: warning đi kèm điều kiện

Một phương thức generic varargs có thể gây **heap pollution** khi kiểu phần tử không reifiable. `-Xlint:varargs` và `-Xlint:unchecked` giúp nhận diện các tình huống cần kiểm tra:

```java
static <T> void showAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Đây là method minh họa trong một class. Tùy ngữ cảnh khai báo và cách gọi, compiler có thể phát warning vì generic varargs sử dụng mảng ở runtime. Không kết luận bất kỳ lần khai báo `T...` nào chắc chắn tạo ra lỗi; lỗi chỉ xuất hiện nếu code thực sự làm điều nguy hiểm với kiểu mảng hoặc lời gọi.

Với một số helper phù hợp điều kiện, `@SafeVarargs` cho phép tác giả **cam kết** method không thực hiện thao tác thiếu an toàn trên varargs array; đây **không phải** cách tắt warning để bỏ qua kiểm tra. Trước khi dùng, xác minh không ghi phần tử sai loại, không làm lộ mảng varargs ra nơi gây heap pollution, và đúng các điều kiện cho phép annotation trong Java đang dùng.

Về hướng thiết kế, có thể nhận `List<T>` hoặc `Collection<T>` thay vì generic varargs nếu API không cần cú pháp truyền đối số linh hoạt.

## 11. Các cảnh báo hữu ích khác tùy kiến trúc

`-Xlint:all` thường mở rộng phạm vi hơn những nhóm ban đầu. Khi đọc các warning phát sinh thêm, nên phân loại:

- **`try`:** vấn đề quanh try-with-resources, chẳng hạn tài nguyên bị bỏ qua hoặc cấu trúc đáng nghi theo khả năng phát hiện của javac. Nó không chứng minh mọi resource đã được đóng đúng theo mọi đường đi runtime.
- **`cast`:** phép cast không cần thiết, có thể làm code dài và che mất ý định.
- **`static`:** truy cập field/method static qua instance; nên dùng tên class để thể hiện static member và tránh nhầm với virtual dispatch.
- **`overrides`, `overloads`:** một số tình huống khai báo method có thể gây nhầm lẫn; những cảnh báo này không thay thế kiểm tra overload resolution theo JLS.
- **`processing`:** những tình huống annotation processing không như mong đợi, ví dụ processor không xử lý annotation mà compiler đang xem xét.
- **`path`, `options`:** những sai lệch ở compiler arguments hoặc đường dẫn, đặc biệt khi build trên CI, JDK khác hoặc hệ điều hành khác.
- **`module` và nhóm liên quan:** có ích với ứng dụng JPMS như named modules, exports, yêu cầu automatic module.

Một số key chỉ có trên phiên bản compiler nhất định. Danh sách cuối cùng phải được xác nhận bằng `javac --help-lint` trên toolchain đang chạy. Không sửa toàn bộ dự án chỉ vì một máy có JDK mới hơn tự bật thêm một số warning.

### Cảnh báo có thể không liên quan trực tiếp đến an toàn

Ví dụ `cast` thừa hay `static` access qua instance không nhất thiết gây lỗi ngay. Chúng vẫn có ý nghĩa vì làm sạch code, giảm hiểu lầm API và thuận lợi cho kiểm tra tự động. Ngược lại, một warning `unchecked` trong tầng deserialize dữ liệu ngoài có thể là rủi ro thực tế cao hơn.

**Chọn nhóm dựa trên codebase và kỳ vọng bảo trì**, không dựa vào con số warning nhiều nhất.

## 12. -Werror, -Xmaxwarns và mức nghiêm ngặt trong CI

Sau khi đã chọn nhóm lint hữu ích, có thể yêu cầu warning làm build thất bại:

```bash
javac --release 17 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -Werror -d out LintClean.java
```

Lệnh đã kiểm chứng với file `LintClean.java` ở mục 5: biên dịch thành công.

Còn với `LintLab.java` ở mục 4, cùng các nhóm warning và `-Werror`, trình biên dịch phát warning rồi báo thất bại vì warnings:

```bash
javac --release 17 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -Werror -d out LintLab.java
```

Không nên dùng một file output từ lần biên dịch cũ làm bằng chứng compile mới thành công. Khi dùng `-Werror`, kiểm tra **exit code** của `javac` và log build; việc thư mục đã có `.class` không đủ chứng minh lượt hiện tại đã qua.

`-Xmaxwarns 10` chỉ giới hạn số warning chi tiết được in; không phải “cho phép tối đa 10 warnings rồi vẫn pass” và không thay ngữ nghĩa của `-Werror`. Compiler có thể thông báo số warning bị ẩn thêm khi bị giới hạn.

### Áp dụng tăng dần trong codebase lớn

1. **Chạy baseline:** compile với nhóm mong muốn, lưu log, đếm/phân loại warning và nguồn gốc.
2. **Sửa code mới trước:** đặt quy tắc cho module hoặc phạm vi do nhóm đang sở hữu, tránh thêm lỗi mới.
3. **Ưu tiên cảnh báo giá trị cao:** như `unchecked` ở ranh giới API, `removal` trước khi nâng JDK, `fallthrough` tại code điều khiển nghiệp vụ.
4. **Giải quyết warning cũ có kế hoạch:** sửa source hoặc nâng dependency, phân biệt code generated/vendor không thuộc quyền kiểm soát.
5. **Bật `-Werror`** cho các module có baseline sạch, test đủ để không gây build thất bại hàng loạt chỉ vì thay đổi môi trường không kiểm soát.
6. **Ghi lại toolchain/version:** khác biệt warning giữa JDK 17 và JDK mới hơn là điều cần kiểm chứng.
7. **Review ngoại lệ:** suppression hoặc disable category phải có lý do và phạm vi cụ thể.

Không đặt mục tiêu “0 warning” bằng mọi giá mà biến build thành im lặng trước lỗi thật. Một baseline có chủ đích cùng vòng phản hồi rõ ràng có giá trị hơn việc vô hiệu hóa diagnostics đồng loạt.

## 13. SuppressWarnings và chọn phạm vi loại trừ

Java cho phép dùng `@SuppressWarnings` để tắt một số warning của compiler trong phạm vi khai báo phù hợp:

```java
@SuppressWarnings("deprecation")
static void callLegacy() {
    // Lời gọi API deprecated có chủ đích trong adapter tương thích.
}
```

Đoạn trên là ví dụ phạm vi annotation, không phải chương trình độc lập. Trong Java thực tế cần code tương ứng và lý do sử dụng API cũ.

Ví dụ nhiều key:

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static void legacyBridge() {
    // Chỉ dùng khi đã xác minh rõ dữ liệu từ API legacy.
}
```

**Không sử dụng đoạn minh họa trên như một cách bỏ qua lỗi kiểu.** Nếu cần chuyển raw `List` sang typed `List<String>`, bạn vẫn phải biết bên trong danh sách có đúng kiểu phần tử không. `@SuppressWarnings` không thêm runtime validation hay sửa lỗi logic.

Những điểm cần nhớ:

- Key trong `@SuppressWarnings` thường dùng dạng `"unchecked"`, `"deprecation"`, `"rawtypes"`, **không thêm tiền tố `-Xlint:`**.
- Không phải mọi loại lint đều có thể bị suppress ở vị trí nguồn. Ví dụ một số warning về command-line options, path hoặc annotation processing không thuộc phạm vi suppression của class/method.
- Suppress **càng hẹp càng tốt**: một method bridge đã được kiểm toán thường tốt hơn tắt nguyên package hoặc toàn module.
- Nếu dùng suppression, ghi rõ nguyên nhân, giả định và cách kiểm soát. Khi môi trường nâng cấp, quay lại đánh giá.
- Thông thường nên **sửa nguyên nhân trước**, dùng suppression như ngoại lệ cuối cùng đã được xét duyệt.

### Tắt nhóm lint trên command line khi thật sự cần

```bash
javac -Xlint:all,-serial -d out LintClean.java
```

Ví dụ này tắt riêng `serial` trong tập `all`. Nếu một codebase có nhiều serializable legacy types đã có chính sách riêng, cách làm này có thể được cân nhắc theo module; nhưng áp dụng mọi nơi sẽ bỏ qua cảnh báo ở code mới. Không chỉ nhìn số warning giảm là kết luận thiết kế tốt hơn.

`-Xlint:none` chỉ nên dùng trong trường hợp cụ thể cần giảm output hoặc tái hiện điều kiện toolchain, và cần hiểu nó **không tương đương “không còn vấn đề”**.

## 14. Đọc diagnostic đúng cách

Với `javac -Xlint:unchecked ...`, một warning thường gồm:

```text
Example.java:12: warning: [unchecked] unchecked conversion
    List<String> values = rawValues;
                          ^
  required: List<String>
  found:    List
```

Đây là **ví dụ hình thức**, không được coi là output của file `Example.java` có thật trong bài. Các phần thường gặp:

1. `Example.java:12`: file và dòng code bị chỉ ra.
2. `warning`: mức diagnostic; nếu là `error` thì bản chất khác.
3. `[unchecked]`: key giúp lọc và định tuyến xử lý.
4. `unchecked conversion`: mô tả thao tác đáng nghi.
5. `^`: vị trí biểu thức liên quan.
6. `required`/`found`: kiểu mong đợi và kiểu compiler tìm thấy.

Quy trình đọc hợp lý: xác định **code line và type**, sau đó tìm chỗ **nguồn dữ liệu** hoặc **kết cấu control flow** tạo ra warning. Đừng chỉ sửa đúng vị trí dấu `^` mà bỏ qua nguyên nhân ở một method hoặc type declaration phía trước.

### Diagnostic không nhất thiết ở stdout

`javac` thông thường viết diagnostic ra **stderr**, trong khi chương trình Java mẫu có thể in ra **stdout**. Vì vậy log CI có thể trộn nhiều dòng; khi báo cáo phải phân biệt output trình biên dịch và output ứng dụng.

Trong môi trường chạy script, kiểm tra **exit code** thay vì grep thông điệp. Mỗi JDK/vendor có thể thay đổi wording, thứ tự, cột và những phần thông tin bổ sung.

## 15. Luyện tập chẩn đoán nhanh

**Bài tập 1 — Đọc warning rawtypes:**

```java
java.util.List items = new java.util.ArrayList<Integer>();
```

Lỗi thiết kế là gì? **Đáp án:** biến `items` dùng raw `List`, làm mất kiểm tra generic. Nếu collection chứa Integer, khai báo `List<Integer> items = new ArrayList<>();` phù hợp hơn.

**Bài tập 2 — Chọn nhóm để chuẩn bị nâng JDK:**

Dự án nhiều thư viện cũ, có nguy cơ API bị loại bỏ. Dùng key nào trước? **Đáp án:** `-Xlint:removal,deprecation` giúp tìm những lời gọi API deprecated hoặc marked for removal; sau đó đối chiếu migration guide.

**Bài tập 3 — Switch có fallthrough:**

```java
switch (level) {
    case 1:
        notifyUser();
    case 2:
        notifyAdmin();
        break;
    default:
        break;
}
```

Đoạn này chỉ minh họa trong một method có `level` và các phương thức tương ứng. Nếu `level == 1`, hai lời gọi nào xảy ra? **Đáp án:** cả `notifyUser()` và `notifyAdmin()`. Nếu điều đó không phải chủ đích, thêm `break` hoặc đổi sang switch rule phù hợp.

**Bài tập 4 — Warning đã trở thành build failure:**

Một file có warning `unchecked`, thêm `-Werror` khiến compile trả exit code thất bại. Có nghĩa code đột nhiên thành lỗi kiểu theo JLS? **Đáp án:** Không. Mã vẫn có warning, nhưng chính sách build yêu cầu không chấp nhận warning. Hãy xem rủi ro của phép toán trước khi suppress.

**Bài tập 5 — Cảnh báo trong code generated:**

Một tool sinh code có nhiều `rawtypes` nhưng các file được sinh lại tự động. Nên sửa trực tiếp từng file generated? **Đáp án:** Thường không. Hãy sửa template/codegen hoặc cấu hình nguồn sinh để tránh warning mới. Nếu chưa thể sửa, áp dụng ngoại lệ cục bộ có phạm vi rõ, không tắt chung toàn dự án.

**Bài tập 6 — -Xmaxwarns:**

Chạy `javac -Xlint:all -Xmaxwarns 5 ...` và chỉ thấy năm warning chi tiết. Có thể kết luận chỉ có năm vấn đề? **Đáp án:** Không. Giới hạn hiển thị không phải giới hạn số lỗi thực, compiler có thể báo còn warning bị ẩn.

**Bài tập 7 — Suppression:**

`@SuppressWarnings("unchecked")` có làm việc cast `(List<String>) rawObject` an toàn hơn ở runtime? **Đáp án:** Không; annotation chỉ ảnh hưởng diagnostic, không kiểm tra hoặc chuyển đổi các phần tử.

## 16. Quy trình thực tế khi thêm -Xlint cho dự án

Ở mỗi module hoặc tập class cụ thể, làm theo các bước:

1. Xác nhận `javac -version`, compiler thực tế đang chạy trong terminal/build/CI và các key hỗ trợ với `javac --help-lint`.
2. Biên dịch bằng `-Xlint:rawtypes,unchecked,deprecation,removal,fallthrough,serial` trước. Điều chỉnh theo source code và runtime; không ép mọi dự án dùng một bộ duy nhất.
3. Đọc warnings theo **file, dòng, category và thao tác**. Đánh dấu các warning đến từ code mình sở hữu, dependency, generated source và cấu hình build.
4. Chọn một warning quan trọng, viết test hoặc ví dụ tối thiểu thể hiện hành vi trước/sau. Với generics, cân nhắc dữ liệu sai kiểu; với fallthrough, kiểm tra nhánh chạy; với deprecation, kiểm tra tương thích API.
5. Sửa nguyên nhân và compile lại; xác nhận warning đó biến mất cùng hành vi chương trình mong đợi.
6. Khi baseline đã sạch và nhóm thống nhất, đưa `-Werror` vào task/module thích hợp; không bật đồng loạt mà bỏ mặc hậu quả build bị chặn.
7. Theo dõi warning mới khi nâng toolchain: một category mới hoặc diagnostic mới có thể cần cập nhật quy tắc.
8. Dùng suppression hoặc tắt một key có chủ đích, có giới hạn và được review, thay vì dùng `-Xlint:none` làm mặc định.

### Khi dùng Maven hoặc Gradle

Trong Maven, Gradle hoặc IDE, compiler có thể được gọi qua task/plugin/toolchain. Hãy truyền **compiler arguments** bằng cơ chế chính thức của công cụ đó để `-Xlint` thực sự đến `javac`. Đừng giả định truyền flag cho JVM chạy build tool tương đương với truyền flag cho compiler.

- **Compiler options:** `-Xlint:...`, `-Werror`, `--release 17`, `-encoding UTF-8`.
- **JVM options:** như `-Xmx` cho daemon/worker/compiler JVM riêng, tùy mô hình tiến trình.

Những hệ thống build có thể đặt Java toolchain khác với `javac` trong terminal. Khi warning xuất hiện riêng trong CI, đối chiếu JDK, source/target release, dependencies, option list và generated code ở đúng job.

## 17. Tổng kết và tài liệu

`-Xlint` có giá trị khi **cảnh báo có ý nghĩa dẫn đến một hành động kiểm chứng được**: sửa generic type, kiểm tra data conversion, thay API cũ, làm rõ control flow, bảo trì serialization contract hoặc điều chỉnh build flags. Một lần chạy `javac` có thể đưa ra nhiều diagnostic, nhưng chất lượng quyết định nằm ở **phân tích nguy cơ, sửa nguyên nhân và bảo toàn hành vi ứng dụng**.

Nguồn chính thống:

- [Oracle JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): cú pháp `-Xlint`, `-Xlint:key`, `-Werror`, `-Xmaxwarns` và ví dụ các nhóm lint.
- [OpenJDK — javac manual](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/man/javac.md): danh mục key theo nguồn hiện tại, giúp nhận ra category thay đổi giữa JDK.
- [Oracle JDK 21 — @SuppressWarnings](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/SuppressWarnings.html): phạm vi và tác dụng suppression.
- [Oracle JDK 21 — @Deprecated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Deprecated.html): `since` và `forRemoval`.
- [JLS Java SE 21 — `4.8 Raw Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8) và [`5.1.9 Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.9): nền tảng của cảnh báo generics.

**Điều cần ghi nhớ:** `-Xlint` giúp nhìn ra vấn đề; `-Werror` giúp thực thi một chính sách; còn việc sửa code đúng và kiểm chứng chức năng mới quyết định warning có thật sự được giải quyết hay không.