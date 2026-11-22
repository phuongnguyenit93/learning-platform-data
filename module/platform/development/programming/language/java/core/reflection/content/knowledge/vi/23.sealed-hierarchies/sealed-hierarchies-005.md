# Phân cấp kết hợp sealed, non-sealed, final, enum và record

## 1. Nhiều dạng kiểu có thể cùng biểu diễn một mô hình

Một mô hình lệnh có thể cần nhiều cách biểu diễn:

- Một record mang dữ liệu của lệnh.
- Một enum biểu diễn các lựa chọn cố định.
- Một class final có phần thực hiện riêng.
- Một nhánh sealed tiếp tục chia thành các trường hợp nhỏ hơn.
- Một nhánh non-sealed cho phép hệ thống mở rộng thêm.

Khi đọc mô hình bằng Reflection, không nên chia mọi kiểu thành hai nhóm “sealed” và “không sealed” rồi dừng lại. Cần kết hợp các thông tin `isSealed()`, `isEnum()`, `isRecord()`, modifier final và các quan hệ trực tiếp.

Một kiểu có thể đồng thời thỏa nhiều thuộc tính: record là class final; enum có thể là final hoặc sealed ngầm định. Các thuộc tính ấy mô tả những khía cạnh khác nhau, không phải các nhãn luôn loại trừ nhau.

## 2. Vì sao thường chọn sealed interface làm gốc chung?

Record có lớp cha trực tiếp là `java.lang.Record`. Enum có lớp cha trực tiếp là `java.lang.Enum` với tham số kiểu tương ứng. Chúng không thể chọn một class nghiệp vụ khác làm lớp cha trực tiếp.

Cả record và enum đều có thể triển khai interface. Vì vậy, nếu muốn một gốc chung chứa trực tiếp cả record, enum và class thông thường, sealed interface là lựa chọn phù hợp.

Ví dụ ý tưởng:

~~~text
Command — sealed interface
  Payload — record, final
  Halt — enum, final ngầm định
  Policy — enum, sealed ngầm định
  SystemCommand — sealed interface
    Reset — final class
    Trace — record, final
  Extension — non-sealed class
    PluginCommand — một ví dụ mở rộng
~~~

Sơ đồ này giữ các quan hệ trực tiếp. `Reset` và `Trace` thuộc nhánh `SystemCommand`; `PluginCommand` thuộc nhánh `Extension`, không phải các mục trực tiếp của `Command`.

Các kiểu con trực tiếp được cho phép của một sealed interface phải phù hợp quy tắc mở rộng: class là final, sealed hoặc non-sealed, kể cả tính chất ngầm định của enum/record; interface con tiếp tục là sealed hoặc non-sealed.

## 3. Record và enum có quy tắc ngầm định riêng

| Dạng kiểu | Final? | Sealed? | Ý nghĩa đối với phân cấp |
| --- | --- | --- | --- |
| Record | Luôn final | Không sealed | Không có lớp con |
| Enum không có hằng nào mang thân lớp riêng | Final ngầm định | Không sealed | Không có lớp con riêng của hằng |
| Enum có ít nhất một hằng mang thân lớp riêng | Không final | Sealed ngầm định | Cho phép các lớp con ẩn danh tương ứng với các thân hằng |
| Class final thông thường | Có | Không sealed | Dừng kế thừa ở class ấy |
| Class/interface sealed | Không phải final đồng thời | Có | Kiểm soát kiểu con trực tiếp |
| Class/interface non-sealed | Không final | Không sealed | Mở lại việc mở rộng ở nhánh ấy |

Với record, không cần viết thêm final để đáp ứng quy tắc của một sealed interface; tính final đã có sẵn. Record không được khai báo sealed hoặc non-sealed.

Với enum, không tự thêm các modifier final, sealed hoặc non-sealed vào khai báo. Java quyết định tính final/sealed từ việc các hằng có thân lớp riêng hay không.

Do đó, chỉ nhìn xem mã nguồn có từ khóa `sealed` ở đầu enum không là chưa đủ. `Class.isSealed()` có thể trả `true` cho enum mà tác giả không viết từ khóa ấy.

## 4. Ví dụ hoàn chỉnh: quan sát cả mô hình bằng Reflection

Lưu thành `MixedSealedHierarchyDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class MixedSealedHierarchyDemo {
    sealed interface Command
            permits Payload, Halt, Policy, SystemCommand, Extension {
    }

    record Payload(String text) implements Command {
    }

    enum Halt implements Command {
        INSTANCE
    }

    enum Policy implements Command {
        STRICT {
            @Override
            int limit() {
                return 1;
            }
        },
        LENIENT;

        int limit() {
            return 10;
        }
    }

    sealed interface SystemCommand extends Command
            permits Reset, Trace {
    }

    static final class Reset implements SystemCommand {
    }

    record Trace(String area) implements SystemCommand {
    }

    static abstract non-sealed class Extension implements Command {
    }

    static final class PluginCommand extends Extension {
    }

    private static String role(Class<?> type) {
        if (type.isEnum()) {
            return "ENUM";
        }
        if (type.isRecord()) {
            return "RECORD";
        }
        if (type.isSealed()) {
            return "SEALED_BRANCH";
        }
        if (Modifier.isFinal(type.getModifiers())) {
            return "FINAL_CLASS";
        }
        return "OPEN_TYPE";
    }

    private static void show(Class<?> type) {
        System.out.println(type.getSimpleName()
                + " role=" + role(type)
                + " sealed=" + type.isSealed()
                + " final=" + Modifier.isFinal(type.getModifiers()));
    }

    private static String directNames(Class<?> sealedType) {
        return Arrays.stream(sealedType.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        show(Command.class);
        Arrays.stream(Command.class.getPermittedSubclasses())
                .sorted(Comparator.comparing(Class::getName))
                .forEach(MixedSealedHierarchyDemo::show);

        show(Reset.class);
        show(Trace.class);
        show(PluginCommand.class);

        System.out.println("Command.direct=" + directNames(Command.class));
        System.out.println("SystemCommand.direct="
                + directNames(SystemCommand.class));

        Class<?>[] policyChildren = Policy.class.getPermittedSubclasses();
        System.out.println("Policy.permitted=" + policyChildren.length);
        System.out.println("Policy.anonymousChild="
                + policyChildren[0].isAnonymousClass());
        System.out.println("STRICT.runtimeEnum="
                + Policy.STRICT.getClass().isEnum());
        System.out.println("STRICT.declaring="
                + Policy.STRICT.getDeclaringClass().getSimpleName());

        System.out.println("Extension.permitted="
                + Extension.class.getPermittedSubclasses());
        System.out.println("PluginCommand.isCommand="
                + Command.class.isAssignableFrom(PluginCommand.class));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 MixedSealedHierarchyDemo.java
java MixedSealedHierarchyDemo
~~~

Kết quả với JDK 17:

~~~text
Command role=SEALED_BRANCH sealed=true final=false
Extension role=OPEN_TYPE sealed=false final=false
Halt role=ENUM sealed=false final=true
Payload role=RECORD sealed=false final=true
Policy role=ENUM sealed=true final=false
SystemCommand role=SEALED_BRANCH sealed=true final=false
Reset role=FINAL_CLASS sealed=false final=true
Trace role=RECORD sealed=false final=true
PluginCommand role=FINAL_CLASS sealed=false final=true
Command.direct=Extension,Halt,Payload,Policy,SystemCommand
SystemCommand.direct=Reset,Trace
Policy.permitted=1
Policy.anonymousChild=true
STRICT.runtimeEnum=false
STRICT.declaring=Policy
Extension.permitted=null
PluginCommand.isCommand=true
~~~

Các tên được sắp xếp trước khi in. Thứ tự mảng do `getPermittedSubclasses()` trả về không được dùng làm thứ tự bắt buộc.

Hàm `directNames` chỉ được gọi với các kiểu đã biết là sealed. Trong công cụ tổng quát, cần kiểm tra sealed hoặc xử lý kết quả null trước khi duyệt.

## 5. Đọc từng loại nút trong kết quả

### 5.1. Record là một kiểu dữ liệu đóng về kế thừa

`Payload` và `Trace` được nhận diện bằng `isRecord()`, đồng thời có modifier final. Chúng không cần từ khóa final trong ví dụ.

“Đóng về kế thừa” không có nghĩa là chỉ có một giá trị. Một record `Payload(String text)` có thể có nhiều instance với dữ liệu khác nhau. Nó chỉ không cho phép một class khác kế thừa để tạo thêm dạng lớp con.

Các kiểu của component bên trong record cũng không tự trở thành cạnh kế thừa. `Payload` có một component `String` không có nghĩa `String` là nhánh con của `Payload`.

### 5.2. Enum đơn giản là final, nhưng có thể có nhiều hằng

`Halt` không có thân lớp riêng trên bất kỳ hằng nào nên final ngầm định. Ví dụ dùng một hằng `INSTANCE`, nhưng enum có nhiều hằng mà không có thân riêng vẫn có tính chất final ấy.

Số hằng enum và số lớp con là hai số khác nhau. Muốn lấy các giá trị enum, dùng `getEnumConstants()`; không dùng mảng permitted để đếm các hằng.

### 5.3. Enum có thân riêng tạo một tầng lớp kỹ thuật

`Policy.STRICT` có thân riêng để ghi đè `limit()`. Java tạo lớp con ẩn danh của `Policy` cho thân ấy, và `Policy` trở thành sealed ngầm định.

Trong ví dụ chỉ `STRICT` có thân riêng, nên danh sách permitted của `Policy` có một lớp. `LENIENT` không tạo một lớp riêng tương ứng.

Đối tượng `Policy.STRICT` có lớp thực tế là lớp con ẩn danh, nên `getClass().isEnum()` là false. `getDeclaringClass()` vẫn trả `Policy.class`, là lớp enum khai báo hằng.

Không dùng tên lớp ẩn danh do compiler tạo làm tên biến thể nghiệp vụ. Quan hệ ấy là metadata lớp hợp lệ, nhưng cần được diễn giải theo mục đích của công cụ.

### 5.4. Nhánh sealed tiếp tục cung cấp các nhánh trực tiếp

`SystemCommand` tiếp tục sealed, nên nó có danh sách trực tiếp riêng gồm `Reset` và `Trace`.

`Reset` là class final thông thường. `Trace` là record final. Hai nút cùng dừng kế thừa nhưng có kiểu khai báo và metadata dữ liệu khác nhau.

Không chỉ kiểm tra final rồi làm mất thông tin record, nếu công cụ còn cần hiển thị component hoặc constructor chuẩn của record.

### 5.5. Nhánh non-sealed mở lại khả năng mở rộng

`Extension` là class abstract non-sealed. Nó không tạo instance trực tiếp vì abstract, nhưng cho phép các class khác mở rộng nhánh.

`PluginCommand` là một ví dụ. Nó là một loại `Command` gián tiếp, nhưng không nằm trong permitted trực tiếp của `Command`.

`Extension.getPermittedSubclasses()` trả null vì Extension không sealed. Null không có nghĩa không tồn tại lớp con; nó không cung cấp một danh sách lớp con cho nhánh mở.

Nhãn `OPEN_TYPE` của hàm `role` chỉ có nghĩa kỹ thuật “không enum/record/sealed/final theo các bước kiểm tra ấy”. Nó không phải bằng chứng tổng quát rằng mọi kiểu nhận nhãn này đều được khai báo bằng từ khóa non-sealed. Trong mô hình cụ thể, ta biết Extension là nhánh non-sealed từ khai báo và vị trí trực tiếp dưới kiểu sealed.

## 6. Phân cấp lớp của JVM và cách trình bày mô hình nghiệp vụ

Cùng metadata có thể được trình bày theo hai mục đích:

**Công cụ xem lớp đã biên dịch:** có thể mở rộng `Policy` để hiển thị lớp con ẩn danh của hằng `STRICT`. Điều này phù hợp khi chẩn đoán hành vi ghi đè hoặc quan hệ lớp.

**Công cụ xem các loại lệnh:** có thể trình bày `Policy` là một loại enum, với các hằng `STRICT`, `LENIENT` là lựa chọn giá trị. Không cần biến lớp ẩn danh của `STRICT` thành một loại lệnh mới có tên nghiệp vụ.

Đó là một chính sách trình bày cần nói rõ, không phải sửa metadata để làm enum hết sealed.

Hàm `role` kiểm tra enum và record trước những thuộc tính tổng quát hơn:

1. Enum: giữ thông tin đó là enum, kể cả khi enum sealed.
2. Record: giữ thông tin component, dù record cũng final.
3. Sealed còn lại: có thể duyệt tiếp các kiểu permitted trực tiếp.
4. Final còn lại: một class kết thúc kế thừa.
5. Kiểu còn lại: đánh dấu điểm mở hoặc cần thêm thông tin.

Nếu kiểm tra `isSealed()` trước và luôn đệ quy như một nhánh nghiệp vụ, công cụ có thể đi vào lớp ẩn danh của enum mà không có ý định đó. Nếu chỉ kiểm tra final trước, record và enum final có thể mất nhãn chuyên biệt.

Không có một thứ tự phân loại duy nhất bắt buộc cho mọi công cụ. Thứ tự trên phục vụ cách trình bày loại lệnh trong bài; một trình xem bytecode có thể giữ đồng thời tất cả cờ và quan hệ thay vì chọn một nhãn chính.

## 7. “Root sealed” không bảo đảm toàn bộ mô hình đóng ở mọi độ sâu

Root kiểm soát các nhánh trực tiếp. Nhánh non-sealed có thể tiếp tục mở rộng bằng các kiểu chưa được công cụ biết trước.

Vì thế, không thể chỉ lấy permitted của `Command` rồi kết luận đã biết mọi class cụ thể có thể là Command. Ít nhất nhánh `Extension` đã khiến suy luận ấy không đúng trong mô hình này.

Ngay cả khi các nhánh đều final hoặc sealed, vẫn phải phân biệt:

- Số kiểu được khai báo với số giá trị/instance.
- Class cụ thể với class abstract và interface.
- Class enum với các hằng enum.
- Class record với dữ liệu có thể mang trong các component.
- Cấu trúc permitted thu được với mức độ đầy đủ của môi trường nạp lớp.

`getPermittedSubclasses()` chỉ trả trực tiếp và có thể bỏ qua mục không lấy được đối tượng Class theo hợp đồng API. Công cụ kiểm toán cần mức bảo đảm cao hơn phải đối chiếu thêm dữ liệu và môi trường phù hợp.

Một danh sách permitted cũng không cung cấp constructor, dữ liệu đầu vào hay quyền tạo đối tượng. Không cố tạo thử mọi nút của sơ đồ chỉ để kiểm tra rằng nó nằm trong phân cấp.

## 8. Những thiết kế và giả định cần tránh

| Giả định hoặc cách làm | Vấn đề |
| --- | --- |
| Dùng một sealed class nghiệp vụ làm cha trực tiếp của cả record và enum | Record và enum đã có lớp cha trực tiếp do Java quy định; dùng interface chung khi cần |
| Tự thêm sealed/final/non-sealed vào khai báo enum | Các modifier ấy không được khai báo tường minh trên enum; tính chất được suy ra theo quy tắc enum |
| Cho rằng record không viết final thì có thể kế thừa | Record final ngầm định |
| Dùng `isSealed() == false` để kết luận không có lớp con | Nhánh non-sealed và lớp thông thường có thể có lớp con |
| Đếm permitted của enum để đếm các hằng | Chỉ phản ánh lớp con của các thân hằng, không phải toàn bộ giá trị enum |
| Dùng `constant.getClass()` làm kiểu enum chung | Hằng có thân riêng có lớp con ẩn danh; dùng `getDeclaringClass()` |
| Mọi nút final đều có cùng cách hiển thị | Record, enum và class final thông thường có metadata và ngữ nghĩa khác nhau |
| Mở rộng mọi enum sealed thành các “loại nghiệp vụ” mới | Lẫn lớp thực hiện của hằng với loại enum trong mô hình |
| Một lần lấy permitted ở root đã liệt kê mọi hậu duệ | Danh sách trực tiếp và nhánh mở không cho phép suy luận ấy |

Khi mô hình có cả class và interface, cũng cần giữ danh tính `Class` thay vì gộp theo tên đơn giản. Các tên dùng trong ví dụ đủ phân biệt trong một tệp; một ứng dụng có nhiều package hoặc bộ nạp lớp có thể phức tạp hơn.

## 9. Tự kiểm tra

1. Vì sao sealed interface là gốc chung phù hợp cho cả record và enum?
2. Một enum không có thân riêng trên hằng là final hay sealed?
3. Nếu chỉ một trong ba hằng enum có thân riêng, số lớp permitted của enum có nhất thiết bằng ba không?
4. Vì sao `Policy` vẫn nhận nhãn enum dù `isSealed()` trả true?
5. `PluginCommand` có cần xuất hiện trong permitted trực tiếp của `Command` không?
6. Record final có nghĩa chỉ có một instance record hay không?
7. Khi viết trình xem bytecode, có thể giữ lớp con ẩn danh của enum trong sơ đồ không?

Đáp án:

1. Record và enum có thể triển khai interface nhưng không thể chọn một class nghiệp vụ khác làm lớp cha trực tiếp.
2. Final ngầm định.
3. Không. Các lớp permitted tương ứng với các thân hằng; trong tình huống ấy chỉ có một thân.
4. “Enum” mô tả dạng kiểu, còn sealed mô tả quan hệ mở rộng; hai thông tin có thể cùng đúng.
5. Không. Nó kế thừa qua nhánh `Extension`.
6. Không. Final chỉ đóng kế thừa; dữ liệu và số instance là chuyện khác.
7. Có. Đó là metadata lớp thực tế; cần ghi rõ mục đích và không tự coi nó là loại nghiệp vụ mới.

## Tài liệu đối chiếu

- [JLS 17 — sealed, non-sealed, final và kiểu con trực tiếp](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2).
- [JLS 17 — Enum final hoặc sealed ngầm định](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9).
- [JLS 17 — Record final và lớp cha trực tiếp](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [Java 17 — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()).
