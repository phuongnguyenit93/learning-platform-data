# Javadoc mô-đun: phân biệt công cụ tạo tài liệu với hợp đồng API được công bố (Java 9+)

## 1. Mục tiêu: Javadoc là công cụ xuất bản, còn API contract là cam kết sử dụng

Trong ứng dụng Java có module (`module-info.java`), một nhà phát triển có thể chạy `javadoc` để tạo các trang HTML mô tả module, package, class, interface và phương thức. Tuy nhiên, **một bộ trang HTML được sinh thành công không tự chứng minh API đã được thiết kế đúng, được công bố đúng phạm vi hoặc giữ tương thích**.

Cần phân biệt rõ hai khái niệm:

- **Công cụ `javadoc` và standard doclet**: đọc mã nguồn, comment Javadoc, cấu hình module và các tùy chọn; tạo trang tài liệu cho tập phần tử được chọn. Nó kiểm tra cú pháp/đường dẫn liên kết tài liệu ở những mức nhất định khi bật doclint.
- **Hợp đồng API được công bố**: tập điểm truy cập và hành vi mà người dùng thư viện có thể dựa vào. Với named module trong JPMS, nó được xác định bởi **module descriptor, phần tử có thể truy cập về mặt Java, kiểu/phương thức và ngữ nghĩa đã cam kết**. Tài liệu Javadoc là một cách công bố/giải thích hợp đồng đó; JDK/compiler/runtime và các test thực thi những khía cạnh kiểm chứng được.

Một API contract bao gồm **cấu trúc** (tên module/package, types, constructor/method signatures, access modifiers, exported packages, phụ thuộc module), và **ngữ nghĩa** (tham số được phép, nullability, giá trị trả về, tác dụng phụ, ngoại lệ, thứ tự, tính bất biến, thread safety, tiền/hậu điều kiện, yêu cầu tương thích). Không phải mọi ngữ nghĩa đều được compiler tự kiểm tra, do đó Javadoc phải rõ và cần đi cùng kiểm thử.

Ví dụ: một phương thức có thể khai báo `String greet(String name)`, nhưng chữ ký không nói được `name==null` có hợp lệ hay không. Nếu tài liệu công bố “không chấp nhận null”, implementation và test cần thực thi điều đó. Ngược lại, việc bật tùy chọn `javadoc --show-packages all` **không tự chuyển package nội bộ thành API truy cập được**.

## 2. Ba lớp cần tách bạch

```text
Mã nguồn và hợp đồng                   Công cụ              Đầu ra
───────────────────────                ───────────          ────────────
module-info.java ──┐
package-info.java ─┤
public/protected ──┼──> javadoc + doclet ──> HTML API docs
Javadoc comments ──┘   + options           module-summary,
                                           package-summary,
                                           class pages...
        |
        v
javac / JPMS kiểm tra module readability,
exports, visibility, type/signature rules
        |
        v
Ứng dụng người dùng + integration / contract tests
kiểm tra hành vi và khả năng tương thích
```

| Nội dung cần xác định | Nguồn có thẩm quyền | `javadoc` làm được gì? | `javadoc` không thay thế được |
| --- | --- | --- | --- |
| Module tồn tại, package nào `exports` | `module-info.java` và module descriptor trong artifact | Hiển thị tên module, danh sách export/package/dependency phù hợp | Quy tắc truy cập của compiler/module runtime |
| Class/method nào callable | `public`/`protected`/`private`, dạng type, module readability/exports | Hiển thị các phần tử được chọn theo visibility/filter | Kiểm tra lời gọi compile được trong module tiêu thụ |
| Điều kiện hợp lệ của tham số, tác dụng phụ, bảo đảm | Hợp đồng do maintainer đặc tả, Javadoc/API specification và test | Xuất bản các mô tả như `@param`, `@return`, `@throws`, `@apiNote` | Chạy thử mọi trường hợp, kiểm tra nghiệp vụ |
| Tài liệu có tạo thành công không | `javadoc` và doclint/build output | Có, phát hiện một số lỗi comment/reference | Chứng minh binary/source compatibility |
| Phiên bản API được hỗ trợ | Chính sách phát hành, artifact, compatibility tests | Hiển thị các tag như `@since` | Bảo đảm không có breaking changes |
| Bên ngoài có quyền reflect vào package? | `opens` / `open module` và các quy tắc access | Có thể mô tả cấu hình | Thay đổi quy tắc deep reflection của JPMS |

**Mấu chốt:** `exports`/`requires` và Java access control quyết định khả năng truy cập có kiểm soát; công cụ xuất HTML chỉ mô tả tập API tùy bộ lọc. Những gì Javadoc **hiện thị** không phải là danh sách quyền truy cập được runtime thực thi một cách độc lập.

## 3. Hợp đồng API của named module được hình thành như thế nào?

### 3.1. Module descriptor: đường biên đầu tiên

Từ Java 9, **Java Platform Module System (JPMS)** cho phép mô tả module bằng `module-info.java`. Ví dụ:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Đoạn này xuất **package `com.example.greetings.api`** cho các module có quyền đọc `com.example.greetings`. Nó **không** xuất các package khác, ví dụ `com.example.greetings.internal`. Những class `public` đặt trong package chưa được export vẫn không thể được truy cập trực tiếp bằng mã nguồn thông thường từ một **named module khác**.

Trong module sử dụng:

```java
module com.example.client {
    requires com.example.greetings;
}
```

`requires` thiết lập **readability** của client tới dependency. Nhưng `requires` đơn thuần không vượt qua giới hạn `exports`. Muốn tham chiếu public type của dependency, đồng thời cần package được export phù hợp.

Một số directive hiện hành cần biết khi xác định phạm vi API:

- `exports p;`: export package `p` cho các module đọc được module hiện tại.
- `exports p to m;`: **qualified export**, chỉ cho phép một hoặc vài module nêu tên; không phải API công khai cho mọi client.
- `requires m;`: module hiện tại cần đọc module `m`.
- `requires transitive m;`: API dependency có thể cần chuyển tiếp readability đến module tiêu thụ. Chỉ dùng khi thiết kế API đòi hỏi và sau khi kiểm tra dependency boundary.
- `opens p;`: cho phép **deep reflection** vào package theo quy tắc JPMS, chẳng hạn framework serialization/DI; **không tương đương `exports`** cho import ở compile time.
- `uses S;` / `provides S with Impl;`: hợp đồng tiêu thụ/cung cấp dịch vụ qua `ServiceLoader`; chúng có ý nghĩa với service API nhưng không tự export package implementation.

### 3.2. Visibility bên trong package cũng quan trọng

Để mã ở module khác gọi một type bình thường, cần xem đồng thời:

1. Module tiêu thụ có đọc module chứa type không? (Thường là `requires`.)
2. Package chứa type có được export cho module tiêu thụ không?
3. Type và member có mức truy cập Java phù hợp không? (`public` hoặc `protected` theo ngữ cảnh kế thừa; constructor, nested type và generic bounds cũng cần phù hợp.)
4. API signature có dùng type từ một module/package không truy cập được hay không?

**`public` chỉ là điều kiện ở cấp Java type/member**; với JPMS nó không tự phá đường biên module. Package tên `internal` cũng chỉ là quy ước; quyền truy cập thực sự do descriptor và access modifiers quy định. Hãy dùng cả cấu trúc module và visibility có chủ đích.

### 3.3. Tài liệu và bytecode không đồng nhất

API contract được lưu trong mã/bytecode và mô tả bằng tài liệu, nhưng hai lớp có khả năng **không khớp**:

- Comment nói “tham số không null” nhưng method không kiểm tra.
- Javadoc nói “trả danh sách không thể thay đổi” nhưng method trả trực tiếp danh sách mutable.
- `@throws IOException` được mô tả nhưng method không khai báo checked exception hoặc không bao giờ phát sinh trường hợp đó.
- Một package được viết tài liệu đầy đủ nhưng không `exports`, nên người dùng module không thể import.
- Một package được `exports` nhưng thiếu tài liệu, nghĩa là API có thể truy cập được mà contract ngữ nghĩa lại mơ hồ.

Vì vậy quy trình tốt cần **đối chiếu source, module descriptor, tài liệu và test**, không dùng “javadoc build PASS” làm bảo đảm duy nhất.

## 4. Vai trò thực tế của công cụ `javadoc`

`javadoc` được phân phối cùng JDK. Với các source module hiện đại, công cụ đọc comment `/** ... */`, phân tích declaration và gọi standard doclet để tạo tài liệu HTML.

Một số nhóm tùy chọn vẫn đang được hỗ trợ:

| Tùy chọn | Mục đích |
| --- | --- |
| `--module-source-path src` | Khai báo cây nguồn của module |
| `--module com.example.greetings` | Chỉ định module cần sinh tài liệu |
| `--release 17` | Biên dịch/phân tích dưới mức API/ngôn ngữ mục tiêu tương ứng khi chạy JDK mới hơn |
| `-d docs` | Thư mục đích cho trang HTML |
| `-encoding UTF-8` | Encoding của mã nguồn và comment |
| `-docencoding UTF-8` / `-charset UTF-8` | Encoding và metadata charset của tài liệu tạo ra |
| `-Xdoclint:all` | Bật các nhóm kiểm tra doclint, ví dụ HTML, reference và một số quy tắc comment |
| `--show-module-contents <value>` | Kiểm soát mức chi tiết nội dung module được hiển thị |
| `--show-packages <value>` | Chọn hiển thị package theo phạm vi |
| `--show-types <value>` / `--show-members <value>` | Điều chỉnh visibility của những phần tử xuất ra |

Các tùy chọn `--show-*` là **bộ lọc trình bày của tài liệu**. Chúng không viết lại `module-info.class`, không đổi `exports`, không cấp quyền reflection và không thay mức access của class/member. Ví dụ dùng `--show-packages all` để tạo tài liệu nội bộ có thể hợp lý, nhưng tài liệu nội bộ nên phân phối riêng để người dùng không nhầm thành public API.

### Doclint có giá trị và giới hạn gì?

`-Xdoclint:all` có thể phát hiện các lỗi như liên kết tag `{@link ...}` sai, cấu trúc HTML comment không hợp lệ hoặc một số phần tài liệu bị thiếu. Lỗi/warning cụ thể phụ thuộc JDK, source và cấu hình. Tuy nhiên **doclint không phải static checker cho mọi hợp đồng ngữ nghĩa**. Nó không biết một method có thực sự thread-safe, có tuân thủ giới hạn latency hay có luôn trả kết quả như comment hứa hay không.

Người bảo trì nên kiểm tra warnings trong CI, đồng thời viết unit/integration/compatibility tests. Nếu yêu cầu phát hành không còn warning, hãy cấu hình build coi warnings liên quan là lỗi theo chính sách CI; đừng mặc định mọi warning khiến `javadoc` trả exit code khác 0.

## 5. Cách viết mô tả API có thể sử dụng như hợp đồng

### 5.1. Javadoc đúng vị trí

- Đặt comment `/** ... */` ngay trước `module` trong `module-info.java` để mô tả module-level contract.
- Đặt mô tả package trong `package-info.java` (khi cần giải thích phạm vi package, bất biến chung, namespace, kiểu dữ liệu).
- Đặt comment `/** ... */` trước public interface/class/method/constructor/field thật sự công bố; viết theo góc nhìn người **sử dụng API**.
- Mô tả cả trường hợp thành công và thất bại; nội dung không cần sao chép nguyên chữ ký Java.

### 5.2. Một số tag chuẩn vẫn dùng hiện nay

| Tag / cú pháp | Viết gì? | Điều không tự xảy ra |
| --- | --- | --- |
| `@param name ...` | Ý nghĩa và giới hạn của tham số/generic type parameter | Không tự chèn validation vào implementation |
| `@return ...` | Ý nghĩa giá trị trả về, null/empty/ordering nếu cần | Không làm kết quả trở thành immutable |
| `@throws IllegalArgumentException ...` | Khi nào API phát sinh lỗi; áp dụng cả unchecked exceptions | Không tự ném exception hay thêm `throws` vào method |
| `{@link SomeType}` / `{@code text}` | Liên kết symbol và định dạng code trong mô tả | Không bảo đảm link ngoài hoặc kiến trúc đúng |
| `@since 1.0` | Phiên bản phát hành đầu tiên mà API được cung cấp | Không thực thi chính sách hỗ trợ phiên bản |
| `@apiNote ...` | Giải thích/sử dụng dành cho caller | Không thay lời hứa trong phần đặc tả nếu diễn giải thiếu rõ |
| `@implSpec ...` | Yêu cầu/cam kết dành cho implementation, đặc biệt khi thiết kế API có kế thừa | Không được compiler kiểm thử tự động |
| `@implNote ...` | Chi tiết implementation hiện hành đáng biết | Không nên biến chi tiết phụ thành lời hứa lâu dài |
| `@deprecated ...` + `@Deprecated` | Hướng dẫn thay thế và đánh dấu API không nên dùng mới | Không tự xóa API hoặc ngăn mọi lệnh gọi |
| `@hidden` | Ẩn phần tử khỏi đầu ra chuẩn khi phù hợp | Không hề thay đổi visibility hoặc module exports |

**Chọn câu chữ cụ thể.** “Nhận chuỗi tên” ít hữu ích hơn “`name` không được null/chỉ chứa whitespace; vi phạm ném `IllegalArgumentException`; giá trị trả về là câu chào đã trim hai đầu”. Những ràng buộc như vậy tạo tiêu chí test và giúp client tránh giả định sai.

### 5.3. Nội dung được công bố nên ổn định ở mức nào?

Không phải mọi comment là cam kết giữ **cùng cách triển khai**. API thường hứa điều kiện đầu vào, hiệu quả quan sát được, ngoại lệ và semantic stability; chi tiết lựa chọn thuật toán/structure nội bộ có thể đổi mà không phá hợp đồng. Tránh lộ tên class nội bộ hay chi tiết database/cache implementation trong trang API nếu caller không cần.

Nếu có thay đổi hành vi quan sát được, hãy đánh giá mức độ breaking change ngay cả khi chữ ký Java vẫn giữ nguyên. Ngược lại, cải tiến thuật toán hay chuyển class implementation sang package khác có thể không phá contract nếu không làm đổi các bảo đảm công khai.

## 6. Ví dụ hoàn chỉnh: một module cung cấp API, một module tiêu thụ

Ví dụ có hai module được biên dịch trên **JDK 17+** và có thể dùng ở các JDK hiện đại. Module thư viện công bố **interface `GreetingService`** và **factory `Greetings`**, nhưng giấu một lớp triển khai trong package không `exports`. Module client chỉ dựa vào API được công bố.

### 6.1. Cấu trúc file nguồn

```text
javadoc-module-demo/
└── src/
    ├── com.example.greetings/
    │   ├── module-info.java
    │   └── com/example/greetings/
    │       ├── api/
    │       │   ├── GreetingService.java
    │       │   └── Greetings.java
    │       └── internal/
    │           └── DefaultGreetingService.java
    └── com.example.client/
        ├── module-info.java
        └── com/example/client/Main.java
```

### 6.2. Module thư viện — `src/com.example.greetings/module-info.java`

```java
/**
 * API chào hỏi dùng trong ví dụ JPMS.
 *
 * <p>Chỉ gói {@code com.example.greetings.api} được xuất cho ứng dụng khác.
 *
 * @since 1.0
 */
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Comment trên `module` sẽ xuất hiện trong tài liệu module. `exports` là **ràng buộc truy cập thực sự**; câu mô tả Javadoc chỉ giúp người đọc hiểu ý định thiết kế.

### 6.3. Interface công bố — `src/com.example.greetings/com/example/greetings/api/GreetingService.java`

```java
package com.example.greetings.api;

/**
 * Hợp đồng tạo câu chào.
 *
 * <p>Giá trị {@code null} hoặc tên chỉ chứa khoảng trắng không được chấp nhận.
 *
 * @since 1.0
 */
public interface GreetingService {
    /**
     * Tạo câu chào tiếng Việt.
     *
     * @param name tên người nhận; không được {@code null} hoặc chỉ chứa khoảng trắng
     * @return chuỗi có dạng {@code "Xin chào, <tên đã loại khoảng trắng hai đầu>!"}
     * @throws IllegalArgumentException nếu tên không hợp lệ
     */
    String greet(String name);
}
```

Chữ ký khai báo một phương thức nhận `String` và trả `String`. Điều kiện đầu vào và định dạng đầu ra được bổ sung bằng Javadoc; đây là phần **ngữ nghĩa mà client dựa vào**, nên implementation phải khớp. `@throws` mô tả một unchecked exception; compiler không bắt buộc khai báo trong `throws` của method.

### 6.4. Factory công bố — `src/com.example.greetings/com/example/greetings/api/Greetings.java`

```java
package com.example.greetings.api;
import com.example.greetings.internal.DefaultGreetingService;

/**
 * Cung cấp điểm tạo dịch vụ chào hỏi.
 * @since 1.0
 */
public final class Greetings {
    private Greetings() {}

    /**
     * Tạo dịch vụ chào hỏi.
     * @return một phiên bản {@link GreetingService} sẵn sàng sử dụng
     */
    public static GreetingService create() {
        return new DefaultGreetingService();
    }
}
```

`Greetings.create()` trả **type API `GreetingService`**, không bắt client import class triển khai. Bản thân module có thể dùng package nội bộ của chính nó; việc không `exports` package đó chỉ hạn chế client bên ngoài.

### 6.5. Implementation nội bộ — `src/com.example.greetings/com/example/greetings/internal/DefaultGreetingService.java`

```java
package com.example.greetings.internal;
import com.example.greetings.api.GreetingService;

/** Chi tiết triển khai, không phải API được export. */
public final class DefaultGreetingService implements GreetingService {
    @Override
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Class trên khai báo `public` vì factory ở package `api` cần tạo instance của nó; song package `internal` **không được export trong module descriptor**. Client ở một named module khác vẫn không được import trực tiếp `DefaultGreetingService`. Đây là ví dụ quan trọng cho khác biệt giữa **`public` ở source** và **API được công bố qua module exports**.

### 6.6. Module client — `src/com.example.client/module-info.java`

```java
module com.example.client {
    requires com.example.greetings;
}
```

### 6.7. Mã client — `src/com.example.client/com/example/client/Main.java`

```java
package com.example.client;
import com.example.greetings.api.Greetings;

/** Khách hàng của API được export. */
public class Main {
    public static void main(String[] args) {
        System.out.println(Greetings.create().greet("  An  "));
    }
}
```

Client chỉ import lớp thuộc package được export. Implementation có thể được thay đổi trong bản phát hành sau mà client không cần biên dịch phụ thuộc vào class nội bộ cụ thể.

### 6.8. Biên dịch và chạy

Từ thư mục `javadoc-module-demo`:

```bash
javac --release 17 -encoding UTF-8 -d out --module-source-path src --module com.example.greetings,com.example.client
java --module-path out --module com.example.client/com.example.client.Main
```

Stdout chính xác của chương trình:

```text
Xin chào, An!
```

`--module-source-path src` cho `javac` biết thư mục nguồn chia theo tên module; `--module` chọn các module cần biên dịch. `--release 17` giữ cho source/API mục tiêu phù hợp Java 17 khi biên dịch trên JDK mới hơn. Khi chạy, `--module-path out` chứa module đã biên dịch; `--module <module>/<main-class>` định vị điểm vào.

**Phép thử truy cập nội bộ:** Nếu thay import trong `Main.java` bằng `import com.example.greetings.internal.DefaultGreetingService;`, việc biên dịch module client thông thường sẽ bị từ chối vì package `internal` không được export. Việc Javadoc của class nội bộ có được tạo bởi một bộ tùy chọn tùy chỉnh nào đó cũng **không thay** quy tắc này.

## 7. Tạo tài liệu Javadoc cho đúng module thư viện

Từ cùng thư mục dự án, chạy:

```bash
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -d docs --module-source-path src --module com.example.greetings
```

Lệnh trên không cần chạy chương trình `Main` và không cần tạo class chạy trước; `javadoc` phân tích nguồn module được chỉ định. Đầu ra chính cần quan sát:

```text
docs/
└── com.example.greetings/
    ├── module-summary.html
    └── com/example/greetings/api/
        ├── package-summary.html
        ├── GreetingService.html
        └── Greetings.html
```

Đây là **các file quan trọng trong cây tài liệu**, không phải danh sách đầy đủ mọi file do standard doclet sinh ra (vẫn có index, script, styles...). Với tùy chọn mặc định để công bố API, trang `DefaultGreetingService.html` trong package `internal` **không xuất hiện** bởi package đó không được export.

Trên JDK 24, cùng source ở mục 6 đã được thử biên dịch với `--release 17`, chạy client và tạo trang `module-summary.html`, `GreetingService.html`, `Greetings.html` thành công bằng `javadoc --release 17 -Xdoclint:all`. Đây là phép thử trên project mẫu; kết quả của thư viện khác phụ thuộc source và cấu hình build riêng.

### Đọc đúng ý nghĩa của các trang

- `module-summary.html`: mô tả module, các dependency/exports được hiển thị và package thuộc phạm vi tài liệu.
- `package-summary.html`: các type trong package đang được standard doclet xuất bản.
- `GreetingService.html`: chữ ký interface, method `greet` và các mô tả `@param`, `@return`, `@throws`.
- `Greetings.html`: factory `create` trả về type API.

**Không suy luận quá mức:** HTML cho biết **cái gì được trình bày tại lần build đó**, theo phiên bản source và các tùy chọn hiển thị. Muốn biết một client cụ thể có thật sự import/call được hay không, phải xét `module-info.java`, access modifiers và thử `javac` trên client module.

## 8. Module-level, package-level và type-level Javadoc khác nhau thế nào?

### Module-level — `module-info.java`

Đặt khái quát mục đích module, phạm vi export, điểm mở rộng/service, yêu cầu version/protocol hay lưu ý sử dụng chung. Module descriptor là mã có ý nghĩa đối với `javac`/JPMS; comment phía trước là mô tả cho con người.

Nếu chỉ đổi comment module-level rồi chạy `javadoc`, bạn có thể thay văn bản `module-summary.html` mà **không thay behavior hoặc exports**. Nếu đổi `exports` trong descriptor nhưng quên cập nhật docs, contract thực tế thay đổi còn tài liệu có thể thiếu nhất quán.

### Package-level — `package-info.java`

Có thể tạo file `src/com.example.greetings/com/example/greetings/api/package-info.java` để mô tả quy tắc chung của package:

```java
/**
 * Giao diện và factory công khai cho dịch vụ chào hỏi.
 *
 * <p>Ứng dụng client chỉ nên phụ thuộc vào các type trong package này.
 *
 * @since 1.0
 */
package com.example.greetings.api;
```

Đây là **file minh họa tùy chọn**; thêm nó vào source tree ở mục 6 trước khi chạy `javadoc` nếu muốn phần mô tả xuất hiện trong trang package. `package-info.java` **không thực hiện `exports`**: package chỉ được công bố nếu module descriptor xuất nó một cách phù hợp.

### Type/method-level — `GreetingService.java`

Dùng comment để định nghĩa **hành vi quan sát được**, kiểu dữ liệu và giới hạn phương thức. Với API có kế thừa/phân tầng implementation, tag `@implSpec`/`@implNote` có thể giúp tách yêu cầu đối với implementation khỏi lời giải thích cho caller. Không mô tả chi tiết nội bộ như thể nó là cam kết chung của interface trừ khi thiết kế thật sự yêu cầu.

Khi viết docs theo nhiều cấp, tránh mâu thuẫn: module hứa “chỉ hỗ trợ tên không rỗng”, method lại nói “null được chấp nhận” sẽ khiến client không biết phải dựa vào đâu. Lý tưởng nhất, lớp mô tả tổng quát và lớp mô tả cụ thể bổ trợ nhau.

## 9. Cấu hình hiển thị không đồng nghĩa thay đổi hợp đồng công khai

Standard doclet có các bộ lọc như `--show-module-contents`, `--show-packages`, `--show-types` và `--show-members`. Chúng hữu ích khi cần tạo **hai bộ tài liệu có mục đích khác nhau**:

1. **API docs cho người dùng thư viện:** công bố các module/package/types/members dự kiến để client sử dụng, thường tập trung vào exported packages và public/protected API. Giữ bộ docs này nhất quán với package export và bảo đảm compatibility.
2. **Docs nội bộ cho người duy trì thư viện:** có thể hiển thị implementation detail hoặc phần không export. Chỉ định bộ lọc phù hợp trong build tài liệu nội bộ và **đánh dấu rõ đây không phải public contract**.

Không nên coi tùy chọn Javadoc “hiển thị tất cả package” là thay thế cho `exports`; cũng không dùng `@hidden` để cố **bảo vệ** class/method khỏi caller. `@hidden` ảnh hưởng đầu ra tài liệu, không thay đổi access ở Java/JPMS. Nếu cần cô lập implementation, dùng package chưa export và giới hạn access đúng thiết kế.

Một ví dụ tương tự: comment `@deprecated` hoặc annotation `@Deprecated` vẫn có thể khiến API được truy cập và biên dịch nhưng tạo warning theo ngữ cảnh. Sự có mặt/ẩn đi của mục trên HTML không phải là công tắc tương thích hay policy tự động.

### API bị lộ ngoài ý muốn

Cần rà soát **từng package được export**. Package `api` có thể vô tình chứa `public` helper mới được thêm vào; nếu nó xuất hiện cho caller và có thể import, về mặt thực tế nó có thể trở thành điểm phụ thuộc mới. Trước khi phát hành, kiểm tra public surface bằng source review, `module-info.java`, Javadoc output và compilation tests.

Đặc biệt cẩn thận khi signature của public API tiết lộ type chỉ có trong package không export; chữ ký nhìn có vẻ hợp lệ bên trong module nhưng gây khó khăn hoặc không dùng được từ client. Thiết kế trả về interface/type thuộc exported API như `GreetingService` của ví dụ giúp giảm phụ thuộc vào implementation.

## 10. Hợp đồng API cần được kiểm tra bằng test và compatibility checks

### 10.1. Kiểm tra tài liệu khác với kiểm tra hành vi

Với `GreetingService.greet`, tài liệu hứa:

- `name` không được `null` hoặc blank.
- Tên hợp lệ được bỏ khoảng trắng ở hai đầu.
- Kết quả là câu chào dạng cố định.
- Tên không hợp lệ ném `IllegalArgumentException`.

`javadoc -Xdoclint:all` có thể xác nhận comment/link/tag có hình thức hợp lệ, nhưng **không chứng minh** implementation thực hiện đủ bốn điều. Hãy viết test hành vi, ví dụ:

```java
GreetingService service = Greetings.create();
assert "Xin chào, An!".equals(service.greet("  An  "));

try {
    service.greet("   ");
    throw new AssertionError("Expected IllegalArgumentException");
} catch (IllegalArgumentException expected) {
    // Đúng theo hợp đồng đã công bố.
}
```

Đoạn trên là **minh họa**, dùng bên trong một class test có `import com.example.greetings.api.GreetingService;` và `Greetings`; biểu thức `assert` chỉ được kiểm tra khi bật `-ea`. Trong test thực tế, nên dùng assertions của framework kiểm thử phù hợp hoặc chủ động ném `AssertionError` để việc kiểm tra luôn chạy trong CI.

### 10.2. Kiểm tra khả năng client compile

Một thư viện module chỉ thực sự phục vụ client nếu client **compile được với artifact đã phát hành** và không dựa vào internal type. Test có thể tạo module mẫu `com.example.client` như mục 6, compile trên module path với `requires com.example.greetings`, gọi interface/factory công khai và thực thi.

Nếu xóa `exports com.example.greetings.api;`, client sẽ không còn import package đó. Lúc này ngay cả khi Javadoc HTML cũ vẫn được lưu trên website, **hợp đồng API thực tế đã thay đổi**. Bản HTML không tự cập nhật artifact hoặc ngăn lỗi.

### 10.3. Source, binary, behavioral compatibility

| Loại tương thích | Ví dụ thay đổi có nguy cơ phá vỡ | Cách kiểm tra |
| --- | --- | --- |
| **Source** | Đổi tên method, xóa `exports`, thay kiểu tham số, thêm overload gây ambiguity | Compile lại client test |
| **Binary** | Xóa/thay descriptor method đang được client bytecode gọi | Chạy client bytecode cũ với phiên bản thư viện mới; dùng công cụ API diff khi cần |
| **Behavioral** | Giữ method signature nhưng thay câu trả về, nhận `null` khác trước, thay exception | Contract tests, regression/integration tests |
| **Module boundary** | Đổi module name, export restriction, service provider declaration | Compile/run client module và test `ServiceLoader` nếu liên quan |
| **Documentation** | Comment sai điều kiện, link hỏng, thiếu thông tin đầu vào/ngoại lệ | `javadoc -Xdoclint:all`, review API docs |

Một tài liệu sinh thành công không tương đương với việc thư viện không có breaking change. Với API phát hành cho bên ngoài, hãy giữ **module descriptors, public signatures, docs và test** trong cùng một thay đổi review, rồi so sánh public surface giữa các phiên bản trước khi phát hành.

## 11. Quy trình công bố tài liệu module đáng tin cậy

1. **Xác định người dùng API:** ứng dụng client, plugin hoặc module nào sẽ gọi? Lựa chọn tên module/package ổn định và phạm vi export rõ ràng.
2. **Thiết kế hợp đồng thực sự:** define types/methods, parameter validation, return semantics, exceptions, concurrency/cancellation/ownership khi cần.
3. **Đặt giới hạn bằng JPMS:** khai báo `exports` đúng package API; giữ implementation trong package chưa export. Dùng `opens` có mục đích rõ nếu framework cần reflection; không mở rộng không cần thiết.
4. **Viết comment Javadoc:** module-level comment, package-level comment nếu hữu ích, class/interface/method docs. Tập trung vào những điều caller được phép dựa vào.
5. **Chạy `javac` và `javadoc`** với phiên bản mục tiêu; ví dụ `--release 17` và `-Xdoclint:all`. Kiểm tra warnings, module-summary và trang API.
6. **Compile client mẫu độc lập:** chỉ import type công khai qua `requires`/`exports`; xác nhận không vô tình phụ thuộc internal package.
7. **Chạy test hành vi:** xác nhận các ràng buộc hứa trong docs và hành vi lỗi. Đặc biệt test trường hợp null/blank, input boundary, expected exceptions.
8. **Rà soát tương thích:** so chữ ký, exports, runtime behavior và chính sách version so với bản đã phát hành; quyết định cách thay đổi contract.
9. **Xuất bản artifact và HTML cùng phiên bản:** tài liệu phải tương ứng với source/artifact release. Giữ release notes rõ cho thay đổi API, nhất là thay đổi có thể phá client.
10. **Duy trì:** sửa docs khi contract thay đổi; không để tài liệu giới thiệu tính năng đã bị xóa hoặc nội dung chỉ còn đúng với implementation cũ.

Trong CI, có thể lưu thư mục tài liệu thành artifact tạm để kiểm tra trước khi publish. Chỉ publish khi dự án đã vượt qua các bước compile, Javadoc, tests và review. Không cần chèn khâu “generate docs” vào runtime service: `javadoc` là công cụ build tài liệu, không tham gia xử lý lời gọi `greet(...)` của ứng dụng.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “Có `javadoc` HTML nghĩa là API được công bố và dùng được” | Bộ lọc có thể đưa phần tử nội bộ vào HTML; client vẫn bị JPMS/access rules giới hạn | Kiểm tra `exports`, visibility và compile client |
| “Thêm `@hidden` sẽ khóa class nội bộ” | Tag chỉ ảnh hưởng trình bày tài liệu | Để package không export và giới hạn accessibility đúng |
| “Class `public` luôn truy cập được ở mọi module” | Cần module readability và package export | Kiểm tra `module-info.java` bên cung cấp/tiêu thụ |
| “`opens` tương đương `exports`” | `opens` phục vụ deep reflection, không mở import Java thông thường | Chọn directive đúng mục đích |
| “Thêm `@throws` sẽ khiến method ném lỗi” | Comment không phải câu lệnh Java hay runtime validation | Implementation phải kiểm tra và test phải chứng minh |
| “Doclint PASS nghĩa là tất cả semantic API đúng” | Doclint kiểm tra cấu trúc tài liệu, không thay behavioral tests | Chạy test trên hợp đồng |
| “Đổi comment không thể ảnh hưởng hợp đồng” | Mô tả có thể là cam kết ngữ nghĩa mà người dùng đang dựa vào | Review thay đổi docs như thay đổi contract nếu nội dung normative |
| “Javadoc chứa internal là bug của JPMS” | Mục đích của document visibility và runtime access khác nhau | Tạo docs internal riêng với bộ lọc phù hợp |
| “Thay implementation private luôn là breaking change” | Nếu public surface và behavior vẫn giữ, client có thể không bị ảnh hưởng | Kiểm thử source/binary/behavior, không chỉ tên class |
| “Giữ chữ ký method là bảo đảm backward compatibility” | Có thể đổi behavior, module exports hoặc dependency semantics | Kiểm tra ba lớp source/binary/behavior và module boundary |
| “Đặt `requires` là đủ để truy cập mọi package của dependency” | Package còn cần export và type/member phải accessible | Kiểm tra đủ ba tầng readability/exports/visibility |
| “Module-level docs thay thế package-info và method docs” | Từng cấp trả lời câu hỏi khác nhau | Viết từ tổng quan module đến contract chi tiết |

## 13. Câu hỏi tự kiểm tra

1. Một class `public` ở package `com.example.greetings.internal` có thể được client named module import không? **Không**, vì package không được export cho client; từ `public` không đủ để vượt qua JPMS boundary.
2. Chạy lại `javadoc` với bộ lọc hiển thị thêm package có làm đổi binary module không? **Không**; nó chỉ thay tập trang HTML được tạo ra.
3. Thêm mô tả `@throws IllegalArgumentException` nhưng không sửa implementation có bảo đảm exception xuất hiện không? **Không**, cần code và tests.
4. Nếu client compile và chạy được nhưng `javadoc` báo link `{@link ...}` lỗi, nên xử lý thế nào? **Sửa tài liệu**; việc client chạy được không cho phép phát hành docs hỏng nếu pipeline yêu cầu chất lượng tài liệu.
5. Nếu sửa từ `exports p;` thành `exports p to trusted.client;` thì sao? Các module khác mất quyền truy cập package; đây là thay đổi compatibility tiềm tàng cho client bên ngoài.
6. Vì sao `Greetings.create()` trả `GreetingService` thay vì `DefaultGreetingService`? Để contract công khai dựa vào exported type và giữ implementation độc lập.

## 14. Tài liệu tham khảo chính thống còn áp dụng

- Oracle Java SE 25: [Công cụ `javadoc`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html) — tạo tài liệu module và standard doclet options.
- Oracle Java SE 25: [Specification of Javadoc documentation comments](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html) — comment syntax, block/inline tags, ý nghĩa tài liệu.
- Oracle Java SE 25: [Công cụ `javac`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — biên dịch module, `--release`, `--module-source-path`.
- Oracle Java SE 25: [`java.lang.Module`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html) — module readability và các khía cạnh module runtime.
- OpenJDK: [JEP 261 — Module System](https://openjdk.org/jeps/261) — thiết kế JPMS được đưa vào Java 9 và tiếp tục có hiệu lực.
