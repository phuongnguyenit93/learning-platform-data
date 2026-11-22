# Tài liệu hóa phương thức ghi đè theo hợp đồng kế thừa bằng Javadoc

> **Java 10 — Javadoc.** Khi một lớp ghi đè (`override`) phương thức của superclass hoặc thực thi phương thức của interface, **hợp đồng mà caller nhìn thấy được xác định bởi API của kiểu cha và các ràng buộc có hiệu lực**. Javadoc của phương thức ghi đè không nên sao chép máy móc hoặc âm thầm thay đổi điều kiện đầu vào, kết quả, ngoại lệ và các cam kết về trạng thái. Công cụ `javadoc` có cơ chế **kế thừa phần mô tả phương thức**, hỗ trợ `{@inheritDoc}`, trong khi `@Override` là annotation giúp `javac` kiểm tra việc ghi đè. Bài này trình bày cách viết hợp đồng ở nơi phù hợp, kế thừa tài liệu an toàn, bổ sung chi tiết triển khai và xác nhận HTML được sinh ra bằng `-Xdoclint:all -Werror` trên JDK hiện đại. Chỉ sử dụng kiến thức còn áp dụng ngày nay; các ví dụ chạy trên JDK 17+.

## 1. Học xong bài này cần làm được gì?

1. Phân biệt **kế thừa hành vi/contract** của phương thức Java với **kế thừa nội dung Javadoc** do standard doclet thực hiện.
2. Biết đặt hợp đồng của API vào **interface** hoặc superclass phù hợp thay vì để mỗi implementation tự mô tả lệch nhau.
3. Viết rõ **preconditions**, **postconditions**, nullability, giá trị trả về, checked/unchecked exceptions, side effects và các bảo đảm về thứ tự/thread-safety khi có liên quan.
4. Biết cách dùng `@Override` để compiler kiểm tra ghi đè, nhưng không nhầm annotation ấy với `{@inheritDoc}`.
5. Hiểu cách standard doclet kế thừa mô tả khi override **không có doc comment** hoặc khi có `{@inheritDoc}`.
6. Biết rằng các phần `@param`, `@return`, `@throws` có quy tắc kế thừa riêng; các checked/unchecked exceptions được xét theo **thành phần documentation bị thiếu**, không đơn giản bởi nhãn “checked”.
7. Hiểu quy tắc đối chiếu tài liệu tham số theo **vị trí** kể cả khi tên parameter khác ở implementation.
8. Dùng `@implSpec`, `@implNote`, `@apiNote` để tách hợp đồng công khai và chi tiết triển khai, biết cách đăng ký custom tags khi sinh HTML.
9. Nhận diện sai lầm tăng precondition, giảm postcondition, phát sinh bất ngờ exception, chuyển từ empty result sang `null` hoặc đổi thread-safety không được phép.
10. Hiểu `{@inheritDoc}` chỉ dành cho **override method docs** ở vị trí hợp lệ; không coi constructor, field, overload hoặc static-method hiding là override.
11. Tạo và kiểm tra ba file Java hoàn chỉnh `NameLookup.java`, `MapNameLookup.java`, `LookupDemo.java`; chương trình có **5 dòng stdout đã kiểm thử**.
12. Dùng `javadoc` sinh HTML để kiểm tra phần hợp đồng có thực sự xuất hiện ở trang implementation, thay vì chỉ dựa vào IDE tooltip.
13. Phân biệt cú pháp Javadoc truyền thống `/** ... */` với **Markdown documentation comments `///`** có từ JDK 23; không đưa cú pháp mới vào code được yêu cầu chạy với Java 17.
14. Biết quy trình review và CI cho các thay đổi API: contract tests, Javadoc DocLint, binary/source compatibility và thẩm định semantic compatibility.
15. Trả lời bài tập về hợp đồng kế thừa, documentation inheritance và lỗi thường gặp.

## 2. Hai sự kế thừa khác nhau: contract và tài liệu

Giả sử có interface `NameLookup`:

```java
public interface NameLookup {
    Optional<String> find(String id);
}
```

Đây là **đoạn minh họa**, thiếu `import java.util.Optional` nên không phải file độc lập. Bản chạy đầy đủ ở phần 7.

Lớp `MapNameLookup implements NameLookup` có thể ghi đè phương thức `find`. Java compiler kiểm tra những điều như:
- phương thức có đúng chữ ký phù hợp override hay không;
- có vi phạm giới hạn access modifier không;
- kiểu trả về có tương thích với quy tắc covariant return type không;
- checked exceptions được khai báo có vi phạm giới hạn của kiểu cha không;
- phương thức final/static/private có thể bị ghi đè không.

Đó là **quy tắc của ngôn ngữ Java**. Nó tồn tại dù cả hai phương thức **không có bất kỳ Javadoc nào**.

Còn standard doclet của `javadoc` có thể lấy mô tả từ phương thức **được ghi đè** để hiển thị trong HTML của phương thức **ghi đè**. Đây là một **quy tắc tạo tài liệu**, không phải thao tác runtime của JVM và không phải cách Java tạo dynamic dispatch.

| Khía cạnh | Override trong Java | Kế thừa Javadoc |
| --- | --- | --- |
| Ai thực hiện? | Ngôn ngữ + compiler/JVM theo JLS | `javadoc` standard doclet |
| Tác dụng | Xác định method override/dynamic dispatch, luật checked exception và kiểu | Tạo mô tả, phần `Parameters`, `Returns`, `Throws` trong docs |
| Có xảy ra khi không có Javadoc? | Có | Docs có thể trống hoặc được tìm từ supertype |
| Có cần `{@inheritDoc}` để JVM gọi đúng method không? | **Không** | Tag dùng để chèn nội dung tài liệu |
| Có cần `@Override` để kế thừa Javadoc không? | `@Override` hữu ích và nên dùng cho kiểm tra compiler | Annotation **không** điều khiển tài liệu |
| Nếu implementation làm trái hợp đồng? | Một số sai lệch bị compiler chặn; semantic violations khác có thể compile | Tài liệu không sửa được hành vi; cần tests và review |

### 2.1. Đặt contract đúng tầng

Với API có nhiều implementation, interface là nơi thích hợp để ghi **những cam kết mà mọi implementation phải tuân theo**:
- Input hợp lệ là gì? `null` có được chấp nhận không?
- Nếu không tìm thấy dữ liệu, trả `Optional.empty()`, danh sách rỗng hay ném ngoại lệ?
- Output có thể là `null` không?
- Có bị thay đổi state, I/O, cache hoặc transaction không?
- Có idempotent hoặc thread-safe không? Chỉ ghi nếu thực sự đảm bảo.
- Các ngoại lệ được hứa/định nghĩa là gì, và khi nào?
- Tình huống kiểm tra tham số diễn ra trước hay sau side effects, nếu contract coi điều đó quan trọng?

Nếu lớp con chỉ thay thuật toán, **không được tự ý thay contract** chỉ vì Javadoc viết mới.

### 2.2. Precondition và postcondition

**Precondition** là điều caller phải thỏa trước khi gọi API. Ví dụ: `id` phải không null và không blank.

**Postcondition** là điều API hứa sau khi xử lý input hợp lệ. Ví dụ: `find(id)` **không bao giờ trả `null`**, trả `Optional.empty()` khi không có kết quả.

Đối với đúng cùng một contract:
- Implementation có thể **chấp nhận thêm input** mà interface không cam kết? Về nguyên tắc, mở rộng miền input được chấp nhận không phá caller tuân contract, nhưng phải cân nhắc consistency/docs; không dựa hành vi mở rộng vào API chung.
- Implementation **không được bí mật từ chối input hợp lệ theo interface**, vì như vậy làm precondition chặt hơn.
- Implementation **không được giảm bảo đảm của kết quả**, ví dụ chuyển `Optional.empty()` thành `null` hoặc trả null trong `Optional.of(null)`.
- Implementation phải tôn trọng các bảo đảm ngoại lệ/side effects/order/concurrency đã công bố.

Đây là cách áp dụng nguyên tắc thay thế kiểu con (behavioral subtyping). Java type checker không thể tự phát hiện mọi vi phạm semantic như vậy.

## 3. Viết hợp đồng ở interface và bổ sung implementation details

### 3.1. Ví dụ về hợp đồng chính xác

```java
/**
 * Finds a display name for a person identifier.
 *
 * <p>Identifiers are case-sensitive. A missing ID produces
 * {@link Optional#empty()}, never a {@code null} return value.
 *
 * @param id a non-null, non-blank identifier
 * @return the display name if found; otherwise an empty optional
 * @throws NullPointerException if {@code id} is null
 * @throws IllegalArgumentException if {@code id} is blank
 * @since 1.0
 */
Optional<String> find(String id);
```

Đây là một **method declaration minh họa thuộc interface**, không phải file độc lập. Nó dùng:
- một câu mở đầu mô tả **ý nghĩa** của phương thức;
- `<p>` cho đoạn văn mới trong **traditional Javadoc comment**;
- `{@link Optional#empty()}` tạo liên kết tới API có thật;
- `{@code null}` hiển thị mã `null` an toàn, không phụ thuộc HTML escaping;
- `@param` ghi rõ ràng buộc input;
- `@return` nói rõ kiểu và ý nghĩa kết quả;
- `@throws` cho hai loại unchecked exceptions mà API cố ý công bố;
- `@since` ghi phiên bản **của API trong thư viện**, không mặc định là phiên bản Java.

**Điều quan trọng:** `@throws` trong Javadoc **không tạo ngoại lệ**. Code thực tế phải ném ngoại lệ tương ứng khi contract yêu cầu. Đồng thời việc method không khai báo `throws NullPointerException` trong chữ ký vẫn đúng vì đây là unchecked exception.

### 3.2. Đặt Javadoc ở đâu?

```java
/**
 * Finds a display name.
 */
@Override
public Optional<String> find(String id) {
    // ...
}
```

Comment bắt đầu bằng `/**` phải **đứng ngay trước declaration**, trước annotation `@Override` và các modifiers. Không đặt Javadoc sau `@Override` rồi trông đợi standard doclet gắn nó với phương thức đúng cách.

Đối với implementation đã có interface contract đầy đủ, viết câu “Finds a display name” lặp lại đôi khi là **dư thừa**. Nên giữ contract từ supertype bằng `{@inheritDoc}` và chỉ bổ sung điều thật sự riêng của implementation.

### 3.3. Contract càng có giá trị khi nêu trường hợp biên

Không nên chỉ viết:
- “Gets name.”
- “Returns a name.”
- “Throws exception on invalid input.”

Các câu này không giải quyết các câu hỏi:
- Nếu ID thiếu thì điều gì xảy ra?
- Input null/blank có hợp lệ không?
- Có phân biệt hoa/thường không?
- Có khi nào return null không?
- Nếu không tìm thấy do timeout, có bị nhầm với “không tồn tại” không?
- Có thể gọi đồng thời không?
- Kết quả là snapshot hay một view có thể thay đổi?

Chỉ ghi những cam kết đã được thiết kế và kiểm thử; không thêm promise giả để Javadoc trông “đầy đủ”.

## 4. `@Override`: tốt cho compiler, không tự tạo contract docs

`@Override` là annotation Java (có retention `SOURCE` theo JLS) giúp compiler báo lỗi nếu declaration không thật sự override/implement theo quy tắc ngôn ngữ.

Ví dụ:

```java
@Override
public Optional<String> find(String id) {
    return Optional.empty();
}
```

Đây là đoạn method minh họa trong một class có `implements NameLookup`. Annotation giúp phát hiện lỗi như viết nhầm tên `findd` hoặc chữ ký không khớp.

Nhưng `@Override` **không**:
- tự copy mọi `@param` vào comment nguồn;
- thay `{@inheritDoc}` ở nơi bạn muốn chèn text;
- bảo đảm những điều hứa trong interface đã được code thực hiện;
- yêu cầu JVM phải tạo một runtime artifact chứa Javadoc;
- cho phép lớp con override `private`, `static` hoặc `final` methods không thỏa quy tắc.

**Ghi nhớ:** **`@Override` kiểm tra quan hệ khai báo, `{@inheritDoc}` làm việc với văn bản tài liệu**.

### 4.1. Overload không phải override

Hai method `find(String id)` và `find(long id)` là **overload** nếu cùng class có cả hai. Một method mới không kế thừa hợp đồng Javadoc của method khác **chỉ vì cùng tên**. Gắn `@Override` cho overload không khớp supertype có thể khiến compile fail.

### 4.2. Constructor, static method và field

- **Constructor không override constructor** của lớp cha; không đặt `{@inheritDoc}` vào Javadoc constructor để mong sao chép contract.
- **Static methods** có thể bị *hiding*, không phải instance override.
- **Fields** có thể bị *hiding*, không phải override method.
- **Private methods** không được override theo nghĩa method contract kế thừa của Java.
- **Final methods** không cho phép override.

Chính vì thế không sao chép `{@inheritDoc}` tùy ý vào mọi declaration; standard doclet sẽ không thể tìm được nội dung hợp lệ theo method override.

## 5. Standard doclet kế thừa phần nào trong phương thức?

Cần phân biệt **document comment thiếu hoàn toàn** với **một số phần comment bị thiếu**.

### 5.1. Không viết Javadoc trên override

Ví dụ minh họa:

```java
@Override
public Optional<String> find(String id) {
    // ...
}
```

Nếu đây thực sự là method override của `NameLookup.find`, standard doclet **có thể tìm và hiển thị documentation** từ supertype tương ứng. Đây là **automatic inheritance by omission**. Không có yêu cầu phải thêm một comment rỗng cho mỗi override chỉ để bật tính năng này.

Tuy nhiên để tài liệu được copy, nội dung mô tả **phải có thể truy cập trong source/documentation model**. Nếu interface chỉ có classfile binary mà không có source doc comment để standard doclet đọc, không nên kỳ vọng công cụ tự kéo văn bản từ website của dependency.

### 5.2. `{@inheritDoc}` trong phần mô tả chính

Nếu implementation cần mô tả riêng sau contract chung:

```java
/**
 * {@inheritDoc}
 *
 * <p>This implementation reads from a stable map snapshot.
 */
@Override
public Optional<String> find(String id) {
    // ...
}
```

Tag `{@inheritDoc}` chèn **main description** đã có ở method cha, rồi tài liệu bổ sung được đặt bên dưới. Câu “This implementation...” phải đúng thực tế và không được sửa nghĩa của “return empty if missing”.

Bạn cũng có thể **không thêm** nội dung main mà dùng `{@inheritDoc}` để thể hiện chủ đích reuse, như trong lab phần 7.

### 5.3. `@param`, `@return` và `@throws`

Theo **JDK 25 Documentation Comment Specification**:
- Với method override, các phần documentation thiếu có thể được coi như có `{@inheritDoc}` tương ứng.
- `@param` cho tham số và type parameter có thể được thừa kế khi thiếu hợp lệ.
- `@return` được thừa kế khi method trả giá trị và super method có phần return description.
- `@throws` cần xem **ngoại lệ có được khai báo trong `throws` clause của method override hay không**, và liệu đã có mô tả tương ứng ở phương thức nguồn.
- Với unchecked exceptions **không có trong `throws` clause**, doclet **không mặc định coi @throws của chúng là phần còn thiếu** để tự động mang sang override.
- Khi muốn chủ động mang mô tả ngoại lệ unchecked vào trang override, hãy ghi **`@throws NullPointerException {@inheritDoc}`** và tương tự cho các ngoại lệ khác.

Ví dụ trong lab:

```java
/**
 * {@inheritDoc}
 *
 * @throws NullPointerException {@inheritDoc}
 * @throws IllegalArgumentException {@inheritDoc}
 */
@Override
public Optional<String> find(String id) {
    // ...
}
```

Đây là method minh họa trong class đã implements `NameLookup`; bản chạy đầy đủ ở phần 7. Phần mô tả chính và hai mô tả `@throws` được kế thừa từ interface. `@param` và `@return` đã được doclet tự lấy vì chúng là phần thiếu có thể kế thừa. Phần này đã được xác nhận bằng HTML Javadoc thực tế với JDK 24.

**Không rút gọn thành câu “checked tự thừa kế còn unchecked thì không”.** Quy tắc chuẩn hiện hành dựa trên những **documentation items** mà overriding declaration còn thiếu và cách exception được khai báo, không chỉ phân loại checked/unchecked.

### 5.4. Cách kế thừa tham số khi đổi tên

Giả sử interface có method `search(String key, int limit)` và lớp con đổi tên parameter thành `search(String q, int size)`. Theo spec, tài liệu `@param` được **đối chiếu theo vị trí**, không dựa vào string tên `key` hay `limit`.

Tuy nhiên nếu comment văn xuôi nhắc “key phải...” thì text đó không tự được sửa thành “q”. Hãy ưu tiên tên parameter thống nhất nếu có thể; nếu khác tên, kiểm tra trang HTML và link references để không tạo mô tả khó hiểu.

### 5.5. `{@inheritDoc}` chỉ có những vị trí hợp lệ

Theo JDK 25 spec, `{@inheritDoc}` chỉ hợp lệ trong **documentation của overriding method** ở:
- main description;
- mô tả của `@param`;
- mô tả của `@return`;
- mô tả của `@throws`.

Không dùng nó trong:
- Javadoc của constructor, field hoặc class nhằm sao chép nguyên description của class cha;
- phần `@since`, `@see` hoặc `@deprecated` với giả định mọi block tags tự hỗ trợ inheritDoc;
- method mới không override một declaration tương ứng;
- override mà supertype không có phần documentation thích hợp để chèn.

**Quan trọng:** JDK 22 bổ sung cú pháp tùy chọn `{@inheritDoc Supertype}` để chỉ rõ supertype trong một số trường hợp. Cú pháp cũ **`{@inheritDoc}`** vẫn là lựa chọn portable cho codebase target Java 17; không dùng cú pháp JDK 22 trong ví dụ chạy bằng JDK17.

### 5.6. Nhiều superinterfaces hoặc superclass

Khi nhiều supertypes có descriptions khác nhau, standard doclet cần quyết định nguồn thừa kế. **Quy tắc tìm kiếm có thể thay đổi theo release của `javadoc`**; JDK 25 spec mô tả rõ algorithm, gồm việc xét superclass, interfaces và `Object` theo một trật tự tìm kiếm xác định.

Không dựa vào giả định “interface nào cũng luôn thắng superclass” trong mọi phiên bản Javadoc. Cách an toàn:
1. Viết contract không xung đột ở các supertypes.
2. Nếu có nhiều nơi cùng định nghĩa method, làm rõ hợp đồng từ type cao nhất phù hợp.
3. Dùng một doc comment tường minh ở overriding method khi cần phân giải.
4. Sinh docs bằng JDK dùng trong CI và **kiểm tra HTML đã chọn đúng contract**.
5. Tránh viết override thực thi một hợp đồng không tương thích với một superinterface khác.

## 6. Bổ sung thông tin về implementation mà không đổi hợp đồng

### 6.1. Phân biệt API contract và implementation details

| Thông tin | Nên đặt ở đâu? | Lý do |
| --- | --- | --- |
| Tham số hợp lệ, định nghĩa kết quả, lỗi | Interface/superclass contract Javadoc | Mọi implementation đều phải tuân |
| Lựa chọn data structure | `@implSpec` hoặc `@implNote` của implementation | Không bắt mọi implementation dùng cấu trúc ấy |
| Chi tiết tối ưu cache, snapshot | `@implNote` hoặc documentation nội bộ khi phù hợp | Không phải bảo đảm public chung nếu không chủ ý |
| Hướng dẫn caller sử dụng API | Main description hoặc `@apiNote` | Hữu ích với người dùng API, không nhất thiết là quy tắc runtime |
| Chính sách version/public lifecycle | `@since`, `@deprecated` và changelog | Không được bịa lịch sử của API |
| Ví dụ đầu vào/đầu ra | `{@code}`, `{@link}`, hoặc `{@snippet}` trên JDK hỗ trợ | Tránh ví dụ mâu thuẫn thực tế |

### 6.2. `@implSpec` và `@implNote` là custom tags khi dùng standard doclet

JDK sources và nhiều dự án dùng các thẻ:
- `@implSpec`: phần **Implementation Requirements** hoặc mô tả algorithm mà một implementation cụ thể tuân theo.
- `@implNote`: phần **Implementation Note** thêm rationale/performance/storage details.
- `@apiNote`: phần **API Note**, giải thích cách dùng/caveat hữu ích cho caller.

Những tags này **không phải Java keywords** và trong nhiều thiết lập chúng là **user-defined Javadoc tags** cần đăng ký bằng option `-tag`. Nếu không đăng ký, JDK 24 `javadoc -Xdoclint:all` có thể báo lỗi **unknown tag. Unregistered custom tag?**, dù `javac` vẫn compile source Java.

Khi sử dụng custom tags trong bài lab, công cụ tài liệu được gọi với:

```bash
javadoc -quiet -Xdoclint:all -Werror -encoding UTF-8 \
  -tag "implSpec:a:Implementation Requirements" \
  -tag "implNote:a:Implementation Note" \
  -d docs -sourcepath src -subpackages demo.docs
```

Đây là **cú pháp POSIX shell** dùng dấu `\` nối dòng. Trên Windows PowerShell, nên chạy trên một dòng (phần 7 có câu lệnh đầy đủ). Giá trị `a` ở cấu hình trên cho phép custom tag trên mọi declarations; trong project lớn có thể hạn chế location theo `javadoc` manual. Dấu `:` phân tách tên tag, vị trí và tiêu đề.

**Không trộn `@implSpec` trong Javadoc của interface contract với ràng buộc mới của một implementation mà caller không được báo.** Một implementation vẫn phải tôn trọng contract công khai, kể cả khi đang mô tả tối ưu riêng.

### 6.3. Nêu đủ, nhưng đừng ghi chi tiết gây phá encapsulation

Ví dụ hợp lý ở implementation:
- “This implementation searches a snapshot copied in the constructor.”
- “Subsequent changes to the input map are not observed.”

Không nhất thiết công bố:
- kích thước buffer nội bộ chưa ổn định;
- số buckets/rehash implementation detail có thể đổi;
- thứ tự nội bộ của `Map.copyOf` (không cam kết iteration order);
- độ phức tạp tuyệt đối `O(1)` nếu chưa được API contract/hardware guarantee;
- cam kết “never allocates” nếu GC/JIT/runtime có thể cấp phát trong thao tác.

Nếu thông tin làm người dùng phụ thuộc vào internal implementation, xem xét liệu nó có thực sự nên thành public contract hay không.

## 7. Ví dụ hoàn chỉnh đã biên dịch và sinh HTML Javadoc

Bộ ví dụ có **ba file trong package `demo.docs`**, sử dụng JDK 17+ và chỉ có Java SE dependencies:
- `NameLookup` khai báo hợp đồng một phương thức.
- `MapNameLookup` ghi đè `find`, dùng `{@inheritDoc}` và hai `@throws ... {@inheritDoc}`; `@implSpec`/`@implNote` mô tả **snapshot**, không thay contract.
- `LookupDemo` kiểm chứng kết quả và vòng đời snapshot.

Bên dưới là **các file đầy đủ**; không phải các snippets chỉ tồn tại trong trí tưởng tượng. Mã này đã biên dịch với **`javac --release 17 -Xlint:all`**, chạy thành công và tạo Javadoc HTML bằng **`-Xdoclint:all -Werror`** trên OpenJDK 24.0.2.

### 7.1. NameLookup.java

Tạo file `src/demo/docs/NameLookup.java`:

```java
package demo.docs;
import java.util.Optional;

/**
 * Provides lookup services for display names.
 * @since 1.0
 */
public interface NameLookup {
    /**
     * Finds a display name for a person identifier.
     *
     * <p>Identifiers are case-sensitive. A missing ID produces
     * {@link Optional#empty()}, never a {@code null} return value.
     *
     * @param id a non-null, non-blank identifier
     * @return the display name if found; otherwise an empty optional
     * @throws NullPointerException if {@code id} is null
     * @throws IllegalArgumentException if {@code id} is blank
     * @since 1.0
     */
    Optional<String> find(String id);
}
```

**Đây là nơi xác định contract:** không null, không blank; khi không tìm thấy thì `Optional.empty()`; return type `Optional<String>` và value không bao giờ là null. `@since 1.0` ở đây chỉ phiên bản của API minh họa, **không phải Java 1.0**.

### 7.2. MapNameLookup.java

Tạo file `src/demo/docs/MapNameLookup.java`:

```java
package demo.docs;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * A lookup backed by an immutable snapshot of a map.
 * @since 1.0
 */
public final class MapNameLookup implements NameLookup {
    private final Map<String, String> names;
    /**
     * Copies the supplied name entries.
     *
     * @param source a map with non-null keys and values
     * @throws NullPointerException if the map, a key, or a value is null
     */
    public MapNameLookup(Map<String, String> source) {
        this.names = Map.copyOf(Objects.requireNonNull(source, "source"));
    }

    /**
     * {@inheritDoc}
     *
     * @implSpec This implementation searches the snapshot using
     * {@link Map#get(Object)}.
     * @implNote Later changes to the original input map do not affect
     * this lookup.
     * @throws NullPointerException {@inheritDoc}
     * @throws IllegalArgumentException {@inheritDoc}
     */
    @Override
    public Optional<String> find(String id) {
        Objects.requireNonNull(id, "id");
        if (id.isBlank()) {
            throw new IllegalArgumentException("blank id");
        }
        return Optional.ofNullable(names.get(id));
    }
}
```

Phân tích:
- `@Override` để `javac` xác minh phương thức ghi đè.
- `{@inheritDoc}` lấy mô tả chính từ interface.
- `@param` và `@return` không viết lại vì standard doclet có thể kế thừa tự động.
- Hai `@throws ... {@inheritDoc}` viết tường minh để mang descriptions unchecked exceptions xuống override HTML.
- `@implSpec` mô tả `Map#get` trên snapshot; `@implNote` nêu hệ quả khi caller sửa original map.
- `Map.copyOf` tạo unmodifiable map chứa cùng entries ở thời điểm sao chép, chứ **không deep-copy mọi object**. Trong ví dụ, keys/values là `String` immutable nên không có vấn đề shared mutable values.
- `String.isBlank()` được thêm từ Java 11; do đó **lab này chạy JDK 17+**, không được quảng cáo là source code tương thích với Java 10.
- Nếu ID null, `Objects.requireNonNull` ném `NullPointerException`; nếu ID blank, code ném `IllegalArgumentException`; nếu ID thiếu, `Optional.ofNullable` trả `Optional.empty()`. Hoàn toàn phù hợp với interface contract.

### 7.3. LookupDemo.java

Tạo file `src/demo/docs/LookupDemo.java`:

```java
package demo.docs;
import java.util.HashMap;
import java.util.Map;

/** Demonstrates a lookup whose contract is documented in an interface. */
public final class LookupDemo {
    private LookupDemo() {}
    /**
     * Runs a deterministic example.
     * @param args ignored command-line arguments
     */
    public static void main(String[] args) {
        Map<String, String> input = new HashMap<>();
        input.put("u1", "An");
        NameLookup lookup = new MapNameLookup(input);
        input.put("u1", "Binh");
        System.out.println("found: " + lookup.find("u1").orElse("none"));
        System.out.println("missing: " + lookup.find("u2").isEmpty());
        try {
            lookup.find(" ");
            System.out.println("blank rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("blank rejected: true");
        }
        try {
            lookup.find(null);
            System.out.println("null rejected: false");
        } catch (NullPointerException expected) {
            System.out.println("null rejected: true");
        }
        System.out.println("caller map changed: " + input.get("u1"));
    }
}
```

**Vì sao example có giá trị?** Caller dùng **reference `NameLookup`**, không phải biết lớp cài đặt. Nó vẫn nhận `Optional` đúng contract. Sau khi caller thay `input` từ `An` sang `Binh`, `MapNameLookup` vẫn trả `An` do map snapshot — đây là một chi tiết implementation đã tài liệu hóa rõ ràng, không phá hợp đồng chung.

### 7.4. Cấu trúc thư mục

```text
project/
└── src/
    └── demo/
        └── docs/
            ├── NameLookup.java
            ├── MapNameLookup.java
            └── LookupDemo.java
```

Tạo thư mục tương ứng trước khi lưu source. Không cần Maven/Gradle cho lab. `javac` cần được gọi từ thư mục `project`, nơi có `src`.

### 7.5. Lệnh biên dịch

Một lệnh **không phụ thuộc shell glob** và chạy được với Bash hoặc PowerShell khi JDK17+ có trong PATH:

```bash
javac --release 17 -Xlint:all -d out src/demo/docs/NameLookup.java src/demo/docs/MapNameLookup.java src/demo/docs/LookupDemo.java
java -cp out demo.docs.LookupDemo
```

`javac` tự tạo `out` nếu môi trường cho phép ghi thư mục (tạo trước nếu build environment yêu cầu). Trên Windows classpath ở đây chỉ có **một thư mục**, nên không cần phân biệt `:` với `;` khi nối nhiều entries.

### 7.6. Stdout chính xác — 5 dòng

```text
found: An
missing: true
blank rejected: true
null rejected: true
caller map changed: Binh
```

Đây là **5 dòng đã được kiểm thử** bằng Java 24.0.2 với chính source tương ứng. Không phụ thuộc locale, timezone, thread scheduling hoặc network. Nếu copy source thay đổi behavior, hãy đối chiếu với contract.

### 7.7. Sinh HTML Javadoc, kiểm tra DocLint và custom tags

Trên Bash/PowerShell, dùng **một dòng** để tránh cú pháp nối dòng của hệ điều hành:

```bash
javadoc -quiet -Xdoclint:all -Werror -encoding UTF-8 -tag "implSpec:a:Implementation Requirements" -tag "implNote:a:Implementation Note" -d docs -sourcepath src -subpackages demo.docs
```

Lệnh này được kiểm chứng bằng **javadoc 24.0.2**:
- không có lỗi compiler hay DocLint;
- sinh `docs/demo/docs/NameLookup.html`;
- sinh `docs/demo/docs/MapNameLookup.html`;
- có phần description kế thừa “Finds a display name...”;
- có `Parameters` và `Returns` đúng từ interface;
- có `Throws` cho `NullPointerException`/`IllegalArgumentException` với text thừa kế;
- có phần **Implementation Requirements** và **Implementation Note**;
- có liên kết “Specified by” về `NameLookup.find`.

Nếu quên `-tag` trong một Javadoc tool chưa đăng ký `@implSpec`/`@implNote`, nó có thể báo **unknown tag**. Phải thêm cấu hình tạo docs, **không xóa bừa hợp đồng** để tắt warning.

### 7.8. Kết quả HTML cần đối chiếu

| Thành phần trong MapNameLookup.html | Nguồn | Ý nghĩa |
| --- | --- | --- |
| “Finds a display name...” | `NameLookup.find` | Main contract được kế thừa |
| “non-null, non-blank identifier” | `@param id` của interface | Caller restriction đúng |
| “the display name if found...” | `@return` của interface | Không null, empty semantics |
| `Throws: NullPointerException` | `@throws ... {@inheritDoc}` | Xác minh input null |
| `Throws: IllegalArgumentException` | `@throws ... {@inheritDoc}` | Xác minh input blank |
| Implementation Requirements | `@implSpec` local | Cách lookup snapshot |
| Implementation Note | `@implNote` local | Sửa map gốc không ảnh hưởng |
| “Specified by” | Method override link | Chỉ rõ quan hệ interface |
| Generated HTML location | `docs/demo/docs/MapNameLookup.html` | Có thể mở trong browser để QA |

**Không chỉ nhìn stdout** rồi coi Javadoc hoàn thành. Runtime có thể đúng mà Javadoc bị thiếu `@return`, sai link, sai tags hoặc không được build vì `-Werror`.

## 8. Chọn cách tài liệu hóa theo mức khác biệt của override

### 8.1. Trường hợp A — implementation không có thông tin bổ sung

Nếu một phương thức đơn giản giữ nguyên contract, không có nghĩa vụ/chi tiết đáng công bố, có thể **không cần viết Javadoc trên override**; standard doclet sẽ dùng docs từ supertype nếu tìm thấy phù hợp.

```java
@Override
public Optional<String> find(String id) {
    // Implementation theo đúng NameLookup contract.
}
```

Đây chỉ là mô phỏng cấu trúc, **không phải method runnable**: comment không phải `return`. Trong code thật phải thực thi đầy đủ contract. Cách này tránh copy/paste một phần mô tả có thể lỗi thời khi interface thay đổi.

### 8.2. Trường hợp B — cần giải thích đặc tính implementation

Sử dụng `{@inheritDoc}` cho contract, `@implSpec`/`@implNote` hoặc một đoạn bổ sung **không xung đột** cho chi tiết:

```java
/**
 * {@inheritDoc}
 *
 * @implNote Results come from a stable snapshot taken at construction.
 */
@Override
public Optional<String> find(String id) {
    // ...
}
```

Đoạn minh họa **không độc lập**, vì `@implNote` cần custom-tag registration và phương thức chưa implement. Bản đầy đủ ở phần 7.

### 8.3. Trường hợp C — cần ghi rõ một phần `@param`/`@return`

Ví dụ, nếu method override giữ contract nhưng muốn có ví dụ cụ thể trong `@return`:

```java
/**
 * {@inheritDoc}
 *
 * @return {@inheritDoc} For example, a missing ID yields
 *         {@code Optional.empty()}.
 */
@Override
public Optional<String> find(String id) {
    // ...
}
```

Đây là **documentation illustration**, không phải chương trình. Nội dung thêm chỉ giải thích bằng ví dụ **tương thích** với return contract. Không viết “returns null if missing” vì như vậy **thay đổi nghĩa** của interface.

### 8.4. Trường hợp D — interface có hợp đồng rộng, implementation muốn thắt chặt

Giả sử interface nói “chấp nhận mọi ID không null”, nhưng một implementation chỉ xử lý IDs bắt đầu bằng `U-` và ném `IllegalArgumentException` với ID khác. Nếu `U-` không được coi là giới hạn hợp lệ trong interface, implementation đã **tăng precondition** và phá substitutability.

Không thể sửa bằng một câu:
```java
/**
 * {@inheritDoc}
 * Only accepts identifiers with prefix U-.
 */
```

Dù Javadoc sinh được, code vẫn vi phạm hợp đồng mà client dùng interface trông đợi. Phương án kiến trúc:
- thay interface contract (có kiểm soát breaking change) nếu mọi implementation và clients đồng ý;
- thiết kế một subtype/API mới có contract rõ và không dùng thay interface khi không thỏa;
- hoặc cho implementation xử lý/chuẩn hóa mọi input hợp lệ của interface.

Javadoc là cách thể hiện, **không thay thế thiết kế contract**.

## 9. Hợp đồng ngoại lệ, nullability và generic return types

### 9.1. Checked exception không được nới tùy tiện

Giả sử supertype có method:
```java
interface Source {
    String read() throws java.io.IOException;
}
```

Đây là đoạn Java độc lập về mặt khai báo type, không có `main`. Implementation có thể:
- giữ `throws IOException`;
- ném một checked subtype hẹp hơn (trong giới hạn Java override rules);
- không khai báo checked exception nếu không phát sinh.

Nhưng không được đổi thành `throws Exception` hoặc một checked exception khác rộng hơn ngoài hợp đồng cho phép. `javac` có thể chặn các vi phạm loại này. Javadoc phải giải thích **khi nào** IOException được ném nếu public method thực sự có thể ném.

### 9.2. Unchecked exception có thể phá contract dù compile được

Các ngoại lệ như `IllegalArgumentException`, `NullPointerException` là unchecked, nên compiler không ép khai báo trong `throws` clause. Điều này không cho phép implementation tùy tiện:
- ném NPE với input mà interface nói là hợp lệ;
- ném IAE ở tình huống interface cam kết trả empty;
- bỏ kiểm tra null khi contract hứa ném NPE một cách nhất quán;
- đổi thứ tự side effects và validation làm caller mất an toàn, khi đó là phần contract.

Đối với unchecked exceptions có ý nghĩa public, viết `@throws` ngay ở contract và **làm cho Javadoc của override thể hiện đầy đủ** bằng tags phù hợp.

### 9.3. Covariant return types không đồng nghĩa đổi postcondition

Java cho phép một số kiểu trả về covariant khi override. Nhưng một kiểu con vẫn không được trả kết quả trái bảo đảm của API.

Ví dụ interface trả `Collection<String>`, subclass trả `List<String>` là hợp lệ về type trong một số declaration; nhưng nếu interface bảo đảm immutable snapshot, subclass không được trả live mutable view trái cam kết.

Với generic `Optional<String>`, việc override trả `null` dù type system cho phép reference null sẽ phá postcondition `never null`. Vì vậy cần **contract tests**.

### 9.4. Không lẫn `@throws` Javadoc và Java `throws` clause

| Thành phần | Mục đích |
| --- | --- |
| `throws IOException` trong signature | Một phần của **Java language type rules** |
| `@throws IOException ...` trong Javadoc | Mô tả khi nào ngoại lệ xảy ra |
| `{@inheritDoc}` trong `@throws` | Sao chép mô tả từ supertype phù hợp |
| `throw new IOException(...)` trong code | Thực sự ném exception khi thực thi |
| `@Override` | Kiểm tra declaration là override |
| `@implSpec`/`@implNote` | Tài liệu cho implementation; không tự gây exception |

Các phần này độc lập nhưng cần nhất quán.

## 10. Class hierarchy, default methods và nhiều implementations

### 10.1. Interface default method có documentation contract

Một `default method` có implementation, nhưng vẫn là API được caller nhìn thấy. Có thể ghi hợp đồng ở interface, và nếu lớp implementing override nó thì cần giữ public behavior hoặc công bố thay đổi có chủ đích.

Ví dụ minh họa:

```java
interface Counter {
    /**
     * Returns a non-negative count of processed items.
     * @return count at the observation point
     */
    default long count() {
        return 0L;
    }
}
```

Đây là interface code hợp lệ. Nếu implementation muốn `count` phản ánh số thực, nó có thể override, nhưng **không nên trả số âm** hoặc hứa linearizable snapshot khi không bảo đảm.

`@implSpec` trong default method đôi khi mô tả thuật toán mặc định; nếu subclass override bằng cách khác, không nên copy như thể thuật toán ấy vẫn được dùng. Đó là lý do phải phân biệt **contract** và **implementation details**.

### 10.2. Một method có thể được khai báo trong superclass và interface

Nếu class extends một superclass và implements thêm interface, các method contracts có thể gặp nhau. Standard doclet có quy tắc tìm kiếm source docs theo hierarchy, phiên bản cụ thể và hình thức override. **Đừng dựa vào tên method giống nhau** để cho rằng một phần documentation chắc chắn được kế thừa từ source mình mong muốn.

Nếu hai contracts mâu thuẫn:
- review thiết kế type hierarchy;
- giải quyết mâu thuẫn semantics của API trước;
- document override tường minh khi cần;
- kiểm tra `javadoc` generated HTML sau build.

### 10.3. Vì sao không sao chép mô tả của mọi override?

Copy-paste khiến ba rủi ro:
1. **Drift:** supertype thay contract, implementation docs cũ không tự cập nhật.
2. **Contradiction:** hai trang Javadoc cùng mô tả `find` nhưng một trang nói return empty, trang kia nói null.
3. **Noise:** implementation docs quá dài, người đọc khó thấy khác biệt thật.

Tuy nhiên **không phải lúc nào chỉ `{@inheritDoc}` là đủ**. Khi class có behavior đáng chú ý trong phạm vi contract, hay một guarantee cụ thể đáng công bố (snapshot, caching, concurrency), cần bổ sung đúng vị trí.

## 11. Javadoc toolchain và tài liệu hiện đại

### 11.1. Traditional Javadoc vẫn hợp lệ trên JDK hiện tại

Syntax:
```java
/**
 * Returns the number of active items.
 *
 * @return number of active items
 */
public long count() {
    return 0L;
}
```

Đây là method minh họa trong class. `/** ... */` là truyền thống, vẫn được **JDK 25** hỗ trợ; không phải legacy chỉ vì đã có cú pháp mới.

### 11.2. Markdown documentation comments có từ JDK 23

**JEP 467** đưa Javadoc Markdown comments vào **JDK 23**: dùng các dòng liên tiếp bắt đầu bằng `///`.

Ví dụ **chỉ áp dụng khi compiler/Javadoc đủ mới (JDK 23+)**:

```java
/// Returns a display name.
///
/// {@inheritDoc}
///
/// @implNote This implementation uses a snapshot.
/// @param id a person identifier
public Optional<String> find(String id) {
    // ...
}
```

**Đây chỉ là minh họa syntax, chưa phải full implementation** và không nên copy nguyên vào lớp chạy `--release 17` vì:
- `///` docs chỉ được standard doclet JDK 23+ hỗ trợ.
- `{@inheritDoc}` phải áp dụng cho **method thực sự override**, có nguồn docs tương ứng.
- `@implNote` vẫn cần custom-tag registration theo toolchain nếu sử dụng.
- Các phần `@param` phải khớp với Java declaration thực tế.
- Code thiếu `return` nên phải hoàn thiện body trước khi compile.

Với project có compiler JDK 17/21, **giữ traditional `/** ... */`**; nó vẫn tốt và portable. Không nâng JDK chỉ để đổi style comment nếu tổ chức không có nhu cầu.

### 11.3. Đừng dùng Javadoc để thay thế formal specification và tests

Javadoc là public documentation surface; nó rất có giá trị nhưng không tự đảm bảo:
- tính thread-safe, lock-free hoặc wait-free;
- không có rò rỉ dữ liệu hoặc side effects;
- transaction atomicity hoặc rollback;
- performance O(1);
- không có lỗi trong reflection/JNI/serialization;
- ABI compatibility của thư viện;
- dữ liệu response hợp lệ ở mọi network/error case.

Những cam kết có rủi ro cao cần **tests, invariants và observability** tương ứng.

### 11.4. Khi nào dùng `{@link}`, `{@code}` và `{@snippet}`?

- `{@link SomeType#method()}` cho liên kết tới declaration hợp lệ.
- `{@code null}`, `{@code Optional.empty()}` để hiển thị code literal; nó không tự tạo hyperlink.
- `{@snippet ...}` có trên các JDK hỗ trợ (JEP 413 từ JDK 18) cho ví dụ code với cơ chế validation/formatting của Javadoc toolchain.
- Nếu chạy `javadoc` trên JDK 17, không dùng `{@snippet}` như thể nó đã có ở đó.
- Không nhét ví dụ runtime sai vào snippet chỉ vì Javadoc có thể render nó đẹp.

Trong bài chạy chính, chỉ dùng traditional comments + `{@link}`/`{@code}`, tương thích JDK 17+.

## 12. Tự động hóa chất lượng Javadoc trong CI

### 12.1. Quality gate đề xuất

| Bước | Công cụ | Điều cần kiểm |
| --- | --- | --- |
| Compile | `javac --release 17 -Xlint:all` | Chữ ký override, type safety, warnings |
| Unit/contract tests | JUnit hoặc Java `main` assert | Preconditions, postconditions, exception types |
| Javadoc generation | `javadoc -Xdoclint:all -Werror` | Links, syntax, missing tags, comment structure |
| Custom tag registration | `-tag implSpec...`/`-tag implNote...` | Không có unknown tag; sections hiển thị |
| HTML inspection | Generated docs / CI snapshot | `Parameters`, `Returns`, `Throws`, “Specified by” |
| API compatibility | Chosen compatibility tool + dependency review | Source/binary breakages |
| Runtime matrix | Supported JDK versions | Behavioral compatibility |
| Review | Maintainers/API owners | Contract không bị âm thầm nới/siết |

Không nên coi `-Xdoclint:all -Werror` là công cụ chứng minh đúng semantics. Nó bắt lỗi **tài liệu và tham chiếu** mà doclet kiểm tra được; nó không biết business behavior nào mới là “đúng”.

### 12.2. Rủi ro khi kế thừa docs từ dependencies

Nếu bạn chỉ có binary `.class` của interface trong dependency, generated docs của implementation có thể **không có main description** để kế thừa. Điều này phụ thuộc việc sources có mặt trên `sourcepath` và mô hình tài liệu của doclet. Build dự án API nên có:
- nguồn của interfaces/supertypes cần document;
- sourcepath/module-source-path được cấu hình đúng;
- links tới external docs có kiểm chứng;
- CI stage để bắt missing inherited descriptions.

**Không cho rằng `-link https://...` sẽ tự động tải và chèn mọi câu Javadoc của method cha** như khi source thật có trên sourcepath.

### 12.3. Một method với nhiều tham số

Ví dụ generic:

```java
interface Copier<T> {
    /**
     * Copies a value.
     *
     * @param source source object, never null
     * @param repeat number of copies, positive
     * @return the copied result
     * @throws IllegalArgumentException if repeat is not positive
     */
    T copy(T source, int repeat);
}
```

Đây là **interface hoàn chỉnh về khai báo**, còn implementation phụ thuộc `T`. Nếu override đổi tham số `source` thành `value` và `repeat` thành `count`, inheritance matching theo vị trí. Đừng copy `@param` text thủ công rồi sửa nhầm thứ tự.

**Không yêu cầu mọi method phải có `@throws`** nếu nó không có ngoại lệ có ý nghĩa public; tài liệu cần đúng thực tế hơn là “đủ số tag”.

### 12.4. Review khi sửa interface contract

Giả sử thay đổi contract `find(null)` từ “throw NPE” thành “return empty”:
- Đây là một **semantic API change**; dù chữ ký phương thức giữ nguyên, các implementations cũ có thể tiếp tục ném NPE.
- Không đơn giản thay một câu Javadoc ở interface rồi coi việc hoàn tất.
- Xác định compatibility impact đối với callers và implementations.
- Cập nhật contract tests chạy cho tất cả implementations.
- Cập nhật release notes/semver theo chính sách thư viện.
- Thử nghiệm behavior trên những JDK được hỗ trợ.
- Cân nhắc tạo phương thức mới nếu cần giữ backward compatibility.

Javadoc phải theo thiết kế và kiểm thử, không đi trước code theo cách gây sai contract.

## 13. Lỗi phổ biến và cách sửa

| Nhận định hoặc cách viết sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`@Override` copy Javadoc từ interface” | Annotation không phải doc inheritance mechanism | Dùng standard doclet + `{@inheritDoc}` hoặc omission |
| “Mỗi override phải copy toàn bộ contract” | Dễ drift và tạo mâu thuẫn | Viết contract ở supertype, kế thừa phần dùng chung |
| “`{@inheritDoc}` biến implementation thành đúng contract” | Docs không sửa runtime behavior | Contract tests và API review |
| “Cứ viết `{@inheritDoc}` trong constructor” | Constructor không override | Viết constructor docs riêng |
| “Overload `find(long)` kế thừa `find(String)`” | Chữ ký khác, không override | Viết docs cho overload |
| “Static method hiding là override” | Không có instance dispatch của method override | Không sử dụng inheritDoc như override method |
| “`{@inheritDoc}` dùng trong mọi block tag” | Spec chỉ cho main/param/return/throws | Đặt đúng vị trí hợp lệ |
| “Unchecked `@throws` luôn được tự kế thừa nếu viết `{@inheritDoc}`” | Missing-item rule không coi unchecked không khai báo là thiếu | Viết `@throws X {@inheritDoc}` khi cần |
| “Tham số đổi tên thì mất docs” | Doclet đối chiếu `@param` theo vị trí | Kiểm tra wording sau inheritance |
| “Không thấy Interface docs thì Javadoc có thể lấy từ classfile” | Source doc text thường không ở bytecode | Cung cấp source để sinh docs |
| “`@implNote` là standard tag luôn tự nhận” | Phải đăng ký trong nhiều toolchains | Cấu hình `-tag` trước khi chạy |
| “Class HTML không có `Specified by` nên compiler chắc không override” | Javadoc model/source scope ảnh hưởng HTML | Compile với `@Override` và kiểm tra đúng docs input |
| “Implementation có thể siết input tùy ý” | Phá behavioral substitutability | Giữ preconditions không chặt hơn |
| “Optional.empty và null giống nhau” | `Optional` API contract không tương đương null | Return empty khi thiếu |
| “Javadoc có `@throws` thì code tự ném exception” | Thẻ chỉ là văn bản | Kiểm thử actual exception |
| “Source code không khai báo checked exception thì override được ném mọi checked exception” | Java override checked-exception constraints | Tuân luật compiler |
| “`@since 1.0` là Java 1.0” | Đây có thể là library API version | Ghi rõ versioning policy |
| “`@implSpec` cho phép vi phạm interface contract” | Implementation notes không thay public API | Không mô tả behavior mâu thuẫn |
| “`-Xdoclint:all` đã chứng minh thread-safety” | DocLint không chứng minh semantics | Concurrency tests / review |
| “JDK17 đã đọc được `///` Markdown Javadoc” | JEP467 từ JDK23 | Traditional docs cho JDK17/21 |
| “Mỗi JDK có cùng supertype-search order” | Standard doclet spec thay đổi theo release | Chọn/Javadoc CI toolchain cụ thể |
| “Mọi `@param` đều cần viết lại ở subclass” | Có kế thừa bằng omission | Chỉ ghi phần bổ sung khi thực sự cần |
| “Map.copyOf là deep copy” | Nó tạo unmodifiable map, không deep-clone values | Không hứa mutable values được clone |
| “Sửa contract của interface không làm ảnh hưởng implementations” | Documentation và behavior có thể lệch | Review contract tests cho mọi lớp |
| “Javadoc warning nên luôn bỏ qua trong CI” | Có thể thiếu docs, broken links | Chặn warnings phù hợp bằng `-Werror` |

## 14. Bài tập có đáp án

### Bài 1 — Phân biệt annotation và inline tag

**Đề:** `@Override` có phải là Javadoc tag thực hiện documentation inheritance không?

**Đáp án:** Không. `@Override` là annotation được compiler kiểm tra; `{@inheritDoc}` là inline Javadoc tag được standard doclet xử lý.

### Bài 2 — Không có comment ở override

**Đề:** Implementation giữ đúng contract và không có Javadoc trên overriding method. Standard doclet có kế thừa method docs không?

**Đáp án:** Có thể, khi quan hệ override thực sự tồn tại và source documentation của supertype có thể tìm được. Đây là automatic inheritance by omission.

### Bài 3 — Có `{@inheritDoc}` ở main

**Đề:** Implementation có comment `/** {@inheritDoc} */`. Điều này có ép Java runtime đổi method dispatch không?

**Đáp án:** Không. Nó chỉ hướng dẫn `javadoc` chèn mô tả chính. Runtime dispatch và compatibility theo Java language/JVM rules.

### Bài 4 — Thừa kế `@param`/`@return`

**Đề:** Interface có đủ `@param id` và `@return`, override dùng `{@inheritDoc}` và không tự khai báo hai tags này. Có được lấy docs không?

**Đáp án:** Theo standard doclet JDK25, những documentation items bị thiếu và có thể inherit sẽ được coi như có `{@inheritDoc}`. Trong lab JDK24, HTML đã chứa hai phần này.

### Bài 5 — Unchecked `@throws`

**Đề:** Interface document `@throws NullPointerException` nhưng không khai báo trong Java `throws` clause. Override chỉ có main `{@inheritDoc}`. Có chắc mô tả NPE hiện ở override page?

**Đáp án:** Không nên giả định. Unchecked exception không được coi là missing `@throws` item nếu không khai báo. Viết rõ `@throws NullPointerException {@inheritDoc}` khi cần đưa text vào override HTML.

### Bài 6 — Thay tên tham số

**Đề:** Interface nhận `String key`, implementation đổi tên thành `String id`. Standard doclet dựa tên hay vị trí để inherit `@param`?

**Đáp án:** Theo **vị trí**. Nhưng văn bản tự do trong mô tả không được tự động đổi mọi chữ `key` thành `id`; cần kiểm tra cách diễn đạt.

### Bài 7 — Constructor

**Đề:** Có thể đặt `{@inheritDoc}` vào constructor của lớp con để lấy docs của constructor lớp cha không?

**Đáp án:** Không. Constructor không override method của superclass. Viết docs mới cho constructor.

### Bài 8 — @implSpec và @implNote

**Đề:** Lab có hai custom tags; `javadoc -Xdoclint:all -Werror` báo `unknown tag`. Cách sửa?

**Đáp án:** Thêm `-tag "implSpec:a:Implementation Requirements"` và `-tag "implNote:a:Implementation Note"` vào lệnh Javadoc hoặc cấu hình build plugin tương đương. Tránh xóa nội dung hữu ích một cách máy móc.

### Bài 9 — Sai postcondition

**Đề:** Interface hứa trả `Optional.empty()` nếu missing; lớp con trả `null`. Javadoc `{@inheritDoc}` có sửa được không?

**Đáp án:** Không. Implementation vi phạm contract. Sửa code trả `Optional.empty()`; thêm test case `missing` và xem generated docs.

### Bài 10 — Siết precondition

**Đề:** Interface chấp nhận mọi non-null, non-blank ID. Lớp con chỉ nhận ID bắt đầu bằng `U-` và ném lỗi với ID hợp lệ còn lại. Có thay thế được không?

**Đáp án:** Không theo hợp đồng hiện có. Đó là tăng precondition. Phải đổi thiết kế/hợp đồng có quản trị hoặc làm implementation chấp nhận mọi input hợp lệ.

### Bài 11 — Checked exceptions

**Đề:** Interface khai báo `read() throws IOException`. Override có được khai báo `throws Exception` không?

**Đáp án:** Không, vì `Exception` rộng hơn và vi phạm luật checked exceptions của Java override. Có thể giữ IOException, dùng subtype phù hợp hoặc không khai báo checked exception.

### Bài 12 — Class name giống nhau

**Đề:** Hai methods cùng tên nhưng khác tham số có tự kế thừa Javadoc của nhau không?

**Đáp án:** Không, đó là overload. Javadoc method inheritance yêu cầu quan hệ override thật sự.

### Bài 13 — Map.copyOf trong lab

**Đề:** Caller đổi input map từ `u1→An` sang `u1→Binh` sau khi khởi tạo `MapNameLookup`. Kết quả `find("u1")` theo lab là gì?

**Đáp án:** Vẫn là `Optional.of("An")`; output `found: An`. `Map.copyOf` tạo snapshot entries ở thời điểm constructor, không phải live view của map gốc.

### Bài 14 — JDK17 và Markdown docs

**Đề:** Dự án compile bằng JDK17. Có nên dùng `///` Markdown Javadoc trong code mới rồi kỳ vọng `javadoc 17` hiểu không?

**Đáp án:** Không. JEP467 Markdown documentation comments được đưa vào JDK23. Với compiler/Javadoc 17 hoặc 21, dùng traditional `/** ... */`.

### Bài 15 — DocLint và kiểm thử

**Đề:** `javadoc -Xdoclint:all -Werror` thành công. Có thể kết luận code thực thi đúng thread-safety và business semantics không?

**Đáp án:** Không. DocLint kiểm tra cấu trúc/link/docs; contract phải được kiểm chứng bằng tests, code review và runtime monitoring khi phù hợp.

### Bài 16 — Supertype docs nằm ngoài sourcepath

**Đề:** `javadoc` chỉ thấy binary của interface từ dependency; method override không có docs như mong đợi. Hành động tiếp theo?

**Đáp án:** Cung cấp source/documentation model phù hợp cho supertype trong `sourcepath`/module source path hoặc viết mô tả tường minh ở override, rồi kiểm tra HTML đầu ra. Không coi link tới website bên ngoài là tự copy text.

### Bài 17 — Thay contract là breaking change?

**Đề:** Sửa interface Javadoc từ `find(null) throws NPE` thành `find(null) returns empty` nhưng không đổi chữ ký. Có thể là breaking change không?

**Đáp án:** Có thể là **semantic breaking change**, vì clients và implementations đang dựa vào behavior cũ. Cần API review, contract tests, version policy và migration plan.

### Bài 18 — Chọn cách tài liệu hóa tốt nhất

**Đề:** Interface có hợp đồng đầy đủ, implementation dùng map snapshot. Viết lại toàn bộ `@param`/`@return` ở implementation hay thừa kế docs rồi bổ sung note?

**Đáp án:** Thừa kế nội dung chung bằng `{@inheritDoc}`/omission, dùng `@implSpec`/`@implNote` cho snapshot, và thêm explicit `@throws ... {@inheritDoc}` cho unchecked exceptions cần hiển thị. Sau đó sinh HTML và review.

## 15. Checklist review và QA

- [ ] Hợp đồng của method được đặt tại type chung phù hợp (interface/superclass).
- [ ] Main description mô tả đúng **hành vi**, không chỉ lặp tên method.
- [ ] `@param` nêu điều kiện input, nullability và trường hợp biên.
- [ ] `@return` nêu rõ result, trường hợp missing/empty/null.
- [ ] `@throws` chỉ ghi ngoại lệ thực sự thuộc contract/implementation phù hợp.
- [ ] Implementation không siết precondition hoặc làm yếu postcondition.
- [ ] Public checked-exception declaration vẫn tuân Java override rules.
- [ ] Method ghi đè có `@Override` để compiler kiểm tra.
- [ ] Không nhầm `@Override` với `{@inheritDoc}`.
- [ ] Sử dụng automatic inheritance khi không có điều bổ sung cần công bố.
- [ ] Khi dùng `{@inheritDoc}`, đặt trong main/param/return/throws của overriding method.
- [ ] Với unchecked `@throws` cần hiện rõ trên override docs, thêm explicit inheritance.
- [ ] Tham số đổi tên được review vì Javadoc match theo vị trí.
- [ ] Không dùng `{@inheritDoc}` cho constructor, field, overload không override, static hiding.
- [ ] Không để docs của hai superinterfaces mâu thuẫn với nhau.
- [ ] `@implSpec`/`@implNote`/`@apiNote` được cấu hình `-tag`/tooling phù hợp.
- [ ] Implementation details không trở thành public guarantees ngoài ý muốn.
- [ ] Tài liệu tham chiếu `{@link}` chỉ tới API có thật, không broken links.
- [ ] Với project JDK17/21 không dùng `///` Markdown docs như cú pháp đã có sẵn.
- [ ] Bộ sources được biên dịch bằng `javac --release 17 -Xlint:all`.
- [ ] `LookupDemo` chạy đúng **5 dòng stdout**.
- [ ] `javadoc -Xdoclint:all -Werror` tạo docs thành công khi đăng ký custom tags.
- [ ] HTML của `MapNameLookup` có main description, Parameters, Returns, Throws, implementation notes và “Specified by”.
- [ ] Có unit/contract tests cho input null, blank, missing và snapshot.
- [ ] Không dùng kết quả DocLint thay cho runtime tests hoặc compatibility review.
- [ ] Source documentation của interfaces supertypes khả dụng trong CI khi cần inherit.
- [ ] Khi contract thay đổi, rà soát mọi implementations và clients trước khi release.

## 16. Tổng kết

**Tài liệu hóa phương thức ghi đè đúng cách bắt đầu từ việc thiết kế một hợp đồng thừa kế ổn định.** Interface hoặc superclass nên mô tả những gì caller có thể tin cậy: input hợp lệ, kết quả, ngoại lệ, side effects và các guarantees quan trọng. Lớp con có thể dùng thuật toán khác nhưng không được phá những lời hứa đó.

**`@Override` và `{@inheritDoc}` phục vụ hai mục đích khác nhau**: compiler xác minh quan hệ override, còn standard doclet xây dựng tài liệu bằng cách tìm/chèn phần mô tả từ supertype. `@param`, `@return` và `@throws` có quy tắc inheritance cụ thể — đặc biệt với unchecked exceptions, không nên giả định mọi phần `Throws` tự xuất hiện nếu chỉ viết `{@inheritDoc}` ở main description.

Ở implementation, **ghi các chi tiết khác biệt bằng `@implSpec`/`@implNote`** (và đăng ký custom tags khi toolchain yêu cầu) thay vì copy nguyên contract. Hoàn thiện bằng **source compilation, generated HTML review, DocLint và contract tests**. Đây là cách làm tiếp tục phù hợp trên JDK hiện đại, bất kể bạn dùng traditional Javadoc hay Javadoc Markdown comments mới có từ JDK23.

## 17. Tài liệu tham khảo chính thức

1. [Oracle Java SE 25 — JavaDoc Documentation Comment Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): quy tắc kế thừa comments bằng omission, `{@inheritDoc}` ở main/param/return/throws, missing item và tìm kiếm supertypes.
2. [Oracle Java SE 25 — The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): options `-tag`, `-Xdoclint`, `-Werror`, `-sourcepath`/`-subpackages` và chuẩn hóa generated docs.
3. [Oracle Java SE 25 — JavaDoc Guide](https://docs.oracle.com/en/java/javase/25/javadoc/javadoc-guide.pdf): traditional/Markdown docs, các loại Javadoc tags và ví dụ `{@inheritDoc}`.
4. [Oracle Java Language Specification 25 — Overriding (by Instance Methods)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.1): method overriding, signature/return/throws rules trong class hierarchy.
5. [Oracle Java Language Specification 25 — @Override](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.4): annotation kiểm tra method override.
6. [Oracle — How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html): hướng dẫn phong cách, preconditions, postconditions, exceptions và tính nhất quán của docs.
7. [OpenJDK JEP 467 — Markdown Documentation Comments](https://openjdk.org/jeps/467): cú pháp `///` từ JDK23, không bắt buộc cho codebase JDK17.
8. [Oracle Java SE 24 — Markdown in Documentation Comments](https://docs.oracle.com/en/java/javase/24/javadoc/using-markdown-documentation-comments.html): Javadoc Markdown và Javadoc tags trong tài liệu.
9. [Oracle Java SE 25 API — Map.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): hợp đồng snapshot của map unmodifiable, không deep-copy objects.
10. [Oracle Java SE 25 API — Optional.empty](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html#empty()): kết quả cho trường hợp không có giá trị.