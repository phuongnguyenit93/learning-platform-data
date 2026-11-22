# Lớp ẩn (hidden classes): package, quyền truy cập và class file không hợp lệ

**Lớp ẩn** (*hidden class*) là một class hoặc interface do JVM định nghĩa từ bytecode trong lúc chạy, thường để phục vụ framework, trình tạo mã động hoặc triển khai nội bộ cần tạo nhiều lớp ngắn hạn. API `MethodHandles.Lookup.defineHiddenClass` xuất hiện từ Java 15 (JEP 371) và **vẫn là API được hỗ trợ trong Java hiện đại**. Ví dụ của bài dùng Java 17+ để phù hợp các bản JDK hiện còn được sử dụng rộng rãi.

Bài này tập trung vào ba hợp đồng dễ nhầm: **(1) bytecode phải thuộc cùng package với lookup class; (2) lookup phải có quyền phù hợp, còn quyền `private` phụ thuộc nest; (3) bytecode sai định dạng phải bị JVM từ chối**, không được coi là một class ẩn hợp lệ. Các phép thử phải tách được lỗi package, quyền truy cập và cấu trúc class file.

## 1. “Ẩn” nghĩa là gì, và không có nghĩa là gì?

Khởi tạo lớp ẩn bằng:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classFileBytes, false);
Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

Đây là **đoạn mã minh họa**, đặt trong một phương thức có quyền xử lý `IllegalAccessException`, với `classFileBytes` chứa toàn bộ class file hợp lệ. API trả về một `Lookup` trỏ vào class mới; `hiddenClass.isHidden()` trả về `true`.

- Class ẩn không có **binary name hợp lệ để lớp khác tham chiếu theo tên**. JVM tạo một tên nội bộ có hậu tố duy nhất; `Class.getName()` thường cho chuỗi dạng `demo.hidden.Template/0x...`. Hậu tố không ổn định và **không được hard-code**.
- `Class.forName(hiddenClass.getName())`, `ClassLoader.loadClass(...)` hoặc `Lookup.findClass(...)` **không thể tìm ra hidden class theo tên đó**. Muốn sử dụng nó, giữ tham chiếu `Class<?>`, `Lookup` hoặc `MethodHandle` đã nhận khi định nghĩa.
- “Ẩn” **không phải** modifier `private` và **không phải** cơ chế sandbox bảo mật. Class ẩn vẫn có loader, package, module, protection domain và vẫn phải tuân theo các quy tắc quyền truy cập, xác minh bytecode.
- Đặt `initialize = true` khiến JVM khởi tạo class khi định nghĩa; `false` chỉ hoãn việc khởi tạo, **không miễn khâu định nghĩa và liên kết (linking)**. Nếu bytecode có lỗi, việc đặt `false` không biến nó thành hợp lệ.
- Mặc định hidden class có thể được JVM dỡ bỏ độc lập khi không còn tham chiếu phù hợp. `ClassOption.STRONG` tăng mối liên hệ tồn tại với class loader; tùy chọn này **không cấp quyền truy cập package hay private**. Tránh giữ vô thời hạn `Class`/`MethodHandle`/`Lookup` nếu chủ đích là cho lớp sinh động được dỡ bỏ.

Điểm phân biệt: `Lookup.defineClass(byte[])` tạo **lớp có tên**, cần `PACKAGE` access; `Lookup.defineHiddenClass(byte[], ...)` tạo **lớp ẩn**, cần **full privilege access**. Hai API có yêu cầu bảo mật và khả năng tra cứu tên khác nhau.

## 2. Hợp đồng package: khớp tên trong bytecode với lookup class

Khi gọi `defineHiddenClass`, JVM đọc `this_class` từ cấu trúc `ClassFile`. Tên lớp trong bytecode phải có **cùng tên package** với `lookup.lookupClass()`; JVM dùng class loader, runtime package, module và protection domain của lookup class để định nghĩa hidden class.

Ví dụ:

| Lookup class | Class trong `byte[]` (tên nhúng trong `this_class`) | Kết quả |
| --- | --- | --- |
| `demo.hidden.HiddenLab` | `demo.hidden.Template` | Hợp lệ nếu các điều kiện khác thỏa |
| `demo.hidden.HiddenLab` | `demo.other.ForeignTemplate` | `IllegalArgumentException` vì khác package |
| `demo.hidden.HiddenLab` | `Template` ở unnamed package | `IllegalArgumentException` vì khác package |
| `demo.hidden.HiddenLab` | Class có bytecode bị cắt hỏng | `ClassFormatError` (cần xem lỗi cấu trúc, không suy đoán package) |

**Runtime package** không chỉ là đường dẫn thư mục hoặc dòng `package` trong file Java: về mặt JVM, danh tính runtime package còn gắn với **defining class loader**. Khi định nghĩa lớp ẩn bằng lookup hợp lệ, JVM gán loader và module phù hợp với lookup class. Không thể dùng việc đặt file `.class` vào thư mục khác để “lách” tên package vốn được mã hóa trong `this_class`.

Lưu ý thêm:

- `Class.getPackageName()` của hidden class vẫn cho package thực sự, ví dụ `demo.hidden`; đây là điều nên assert trong test.
- Hậu tố `/0x...` của `Class.getName()` là phần do JVM tạo cho class ẩn, **không phải package**; không lấy hậu tố này để so sánh package.
- Một class file nguồn hợp lệ có thể được dùng để định nghĩa **nhiều hidden class riêng biệt**. Đừng kiểm tra bằng cách kỳ vọng tên hoặc identity của các hidden class phải bằng nhau.
- Package giống nhau về **chuỗi tên** chưa đủ để suy luận quyền truy cập giữa hai class tùy ý do **hai class loader khác nhau** định nghĩa. Luôn kiểm tra runtime package và môi trường loader thực tế.

## 3. Quyền Lookup, package-private và private/nestmate

`MethodHandles.Lookup` là một đối tượng năng lực truy cập (*capability*) gắn với lookup class và các `lookupModes`. `defineHiddenClass` yêu cầu lookup có **full privilege access** — tức khả năng `PRIVATE` **và** `MODULE`. Trường hợp thiếu quyền, API ném `IllegalAccessException`, ngay cả khi `byte[]` là class file hợp lệ.

- `MethodHandles.lookup()` được gọi **ngay trong class chủ sở hữu** thông thường cho lookup có đủ quyền đối với class đó.
- `MethodHandles.publicLookup()` chỉ có quyền công khai hạn chế, **không được dùng** để định nghĩa hidden class.
- `lookup.in(Other.class)` có thể giảm quyền; nó không phải cách “nâng quyền”. `dropLookupMode(...)` cũng chỉ làm mất quyền.
- `MethodHandles.privateLookupIn(target, callerLookup)` có điều kiện về module và `opens`. Đặc biệt, khi di chuyển lookup **qua ranh giới module**, lookup trả về có thể mất `MODULE` access, vì thế dù có quyền truy cập private vào target, vẫn **không đủ full privilege** để định nghĩa hidden class. Giải pháp rõ ràng thường là để class nằm trong **module đích** cung cấp một factory đáng tin cậy.

### Cùng package khác cùng nest

| Thành viên cần truy cập | Hidden class cùng runtime package | Tác động của `ClassOption.NESTMATE` |
| --- | --- | --- |
| `public` | Theo quy tắc truy cập JVM/module thông thường; bản thân hidden class vẫn không tra cứu theo tên | Không cần để có quyền public |
| Không khai báo modifier (*package-private*) | Có thể truy cập nếu cùng runtime package | Không cần |
| `protected` | Phụ thuộc cùng package hoặc quan hệ kế thừa và quy tắc JVM | Không tự bỏ qua quy tắc `protected` |
| `private` của **class khác** | Không đủ chỉ nhờ cùng package | Cho phép truy cập `private` **nếu hidden class được thêm vào cùng nest hợp lệ** |

Một hidden class **mặc định là nest riêng của nó**. Nếu truyền `MethodHandles.Lookup.ClassOption.NESTMATE`, nó tham gia nest của **lookup class**; lúc đó các thành viên trong cùng nest có thể truy cập `private` lẫn nhau. Không nên nhầm `NESTMATE` với việc tự động được quyền truy cập mọi `private` trong cùng package hoặc mọi module.

Ngoài ra, `Lookup` được trả về bởi `defineHiddenClass` có full privilege đối với **hidden class mới**. Điều đó không có nghĩa nó được phép truy cập `private` của mọi class khác; cần áp dụng đúng quy tắc nest/member. Nếu framework nhận bytecode từ nguồn không tin cậy, không trao lookup đặc quyền hay quyền `NESTMATE` một cách tùy tiện. Bytecode verifier không phải sandbox.

## 4. Chương trình chạy độc lập: 5 hợp đồng cần kiểm thử

Ví dụ sau dùng **JDK 17+** và không cần thư viện ngoài. Tạo ba file đúng tên/thư mục như minh họa. File đầu có quyền tạo lookup ngay trong package `demo.hidden`.

**File `src/demo/hidden/HiddenLab.java`:**

~~~java
package demo.hidden;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenLab {
    static String packageMessage() {
        return "package-ok";
    }

    private static String secret() {
        return "private-ok";
    }

    static byte[] classBytes(String resource) throws IOException {
        ClassLoader loader = HiddenLab.class.getClassLoader();
        try (InputStream input = loader.getResourceAsStream(resource)) {
            if (input == null) {
                throw new IOException("Missing class resource: " + resource);
            }
            return input.readAllBytes();
        }
    }

    static String invokeStaticString(
            MethodHandles.Lookup lookup,
            Class<?> owner,
            String name) throws Throwable {
        MethodHandle handle = lookup.findStatic(
                owner, name, MethodType.methodType(String.class));
        return (String) handle.invokeExact();
    }

    public static void main(String[] args) throws Throwable {
        byte[] local = classBytes("demo/hidden/Template.class");
        MethodHandles.Lookup host = MethodHandles.lookup();

        // Thành công: bytecode thuộc đúng package và host đủ quyền.
        MethodHandles.Lookup hiddenLookup =
                host.defineHiddenClass(local, false);
        Class<?> hidden = hiddenLookup.lookupClass();
        System.out.println("hidden=" + hidden.isHidden());
        System.out.println("package=" + hidden.getPackageName());
        System.out.println("package member=" +
                invokeStaticString(hiddenLookup, hidden, "message"));

        // Cùng package nhưng KHÔNG cùng nest: thiếu quyền private.
        try {
            invokeStaticString(hiddenLookup, HiddenLab.class, "secret");
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "private without NESTMATE=IllegalAccessException");
        }

        // Có NESTMATE: hidden class vào nest của HiddenLab.
        MethodHandles.Lookup nestmate = host.defineHiddenClass(
                local, false, MethodHandles.Lookup.ClassOption.NESTMATE);
        System.out.println("private with NESTMATE=" +
                invokeStaticString(nestmate, HiddenLab.class, "secret"));

        // Class ẩn không thể tìm được bằng tên động do JVM tạo.
        try {
            Class.forName(hidden.getName());
            throw new AssertionError("Expected ClassNotFoundException");
        } catch (ClassNotFoundException expected) {
            System.out.println("Class.forName=ClassNotFoundException");
        }

        // Lookup không đủ đặc quyền.
        try {
            MethodHandles.publicLookup().defineHiddenClass(local, false);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("public lookup=IllegalAccessException");
        }

        // Class file hợp lệ nhưng thuộc package khác.
        byte[] foreign = classBytes("demo/other/ForeignTemplate.class");
        try {
            host.defineHiddenClass(foreign, false);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("other package=IllegalArgumentException");
        }

        // Bytecode bị cắt/hỏng, không phải cấu trúc ClassFile.
        try {
            host.defineHiddenClass(new byte[] {0, 1, 2, 3}, false);
            throw new AssertionError("Expected ClassFormatError");
        } catch (ClassFormatError expected) {
            System.out.println("invalid bytes=ClassFormatError");
        }
    }
}
~~~

**File `src/demo/hidden/Template.java`:**

~~~java
package demo.hidden;

final class Template {
    static String message() {
        return HiddenLab.packageMessage();
    }
}
~~~

Class `Template` gọi phương thức `packageMessage` không khai báo `public` của `HiddenLab`, nên là ví dụ thực tế về **package-private access**. Sau khi định nghĩa thành hidden class cùng runtime package, mã này vẫn được phép gọi phương thức đó.

**File `src/demo/other/ForeignTemplate.java`:**

~~~java
package demo.other;

public final class ForeignTemplate {
}
~~~

Lệnh biên dịch/chạy từ thư mục chứa `src`, với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -d out src/demo/hidden/HiddenLab.java src/demo/hidden/Template.java src/demo/other/ForeignTemplate.java
java -cp out demo.hidden.HiddenLab
~~~

**Stdout dự kiến** khi dùng các file trên và môi trường Java 17+ tiêu chuẩn:

~~~text
hidden=true
package=demo.hidden
package member=package-ok
private without NESTMATE=IllegalAccessException
private with NESTMATE=private-ok
Class.forName=ClassNotFoundException
public lookup=IllegalAccessException
other package=IllegalArgumentException
invalid bytes=ClassFormatError
~~~

Để ý rằng chương trình **không** in `hidden.getName()` vì phần hậu tố có thể thay đổi giữa các lần chạy. Mọi nhánh thất bại đều bắt **kiểu ngoại lệ dự kiến**; nếu bất ngờ thành công, chương trình ném `AssertionError` để việc kiểm thử không báo sai là PASS.

Với trường hợp `private`, hai hidden class được tạo từ **cùng bytes**. Nhánh không có `NESTMATE` không thể lấy method handle đến `HiddenLab.secret()`; nhánh có `NESTMATE` được quyền truy cập vì thuộc đúng nest. Điều này cho thấy lỗi quyền không liên quan đến việc class file có hợp lệ hay không.

## 5. Phân loại class file không hợp lệ và thời điểm JVM từ chối

Không phải mọi lỗi `defineHiddenClass` đều là “hỏng bytecode”. Theo hợp đồng API, cần phân biệt:

| Tình huống | Loại lỗi cần kiểm thử | Diễn giải và hướng xử lý |
| --- | --- | --- |
| `byte[]` không tạo thành cấu trúc `ClassFile` hợp lệ (magic sai, bị cắt, constant pool hỏng) | `ClassFormatError` | Sửa bước tạo/đọc bytecode; bảo đảm không đọc thiếu dữ liệu |
| Major/minor class-file version JVM hiện tại không hỗ trợ | `UnsupportedClassVersionError` | Dùng JDK mục tiêu phù hợp hoặc sinh class file đúng mức phiên bản; không sửa header tùy tiện |
| `this_class` thuộc package khác với lookup class | `IllegalArgumentException` | Sinh lại tên nhúng trong class file hoặc đặt factory/lookup ở package thích hợp |
| Bytecode không đại diện class/interface thông thường, ví dụ cờ `ACC_MODULE` | `IllegalArgumentException` | Không dùng `module-info.class` làm hidden class |
| Lookup thiếu full privilege | `IllegalAccessException` | Gọi trong chủ sở hữu có thẩm quyền hoặc sửa thiết kế cấp lookup |
| Class file đúng cấu trúc nhưng bytecode không thỏa verifier | `VerifyError` | Kiểm tra stack map frames, types, luồng điều khiển và chương trình sinh mã |
| Kiểu khai báo làm superclass lại là interface hoặc superinterface lại là class | `IncompatibleClassChangeError` | Kiểm tra cấu trúc phân cấp đã sinh và dependency |
| Class/interface gây vòng kế thừa trực tiếp hay gián tiếp | `ClassCircularityError` | Sửa sơ đồ kế thừa |
| Không thể liên kết vì lý do khác | `LinkageError` hoặc subclass phù hợp | Kiểm tra classpath/module path, tham chiếu và liên kết |
| `bytes` hay một tham số bắt buộc là `null` | `NullPointerException` | Xác thực đầu vào trước khi gọi |
| Muốn tìm hidden class qua `Class.forName` | `ClassNotFoundException` **từ lời gọi tra cứu theo tên**, không phải lỗi tạo class | Giữ `Class`/`Lookup`/`MethodHandle`, tránh lookup bằng tên |

**Phân biệt quan trọng:** `UnsupportedClassVersionError` là một nhánh của `ClassFormatError` trong hệ phân cấp lỗi JVM. Nếu muốn assert chính xác loại lỗi trong test, dùng `assertThrowsExactly` (khi test framework hỗ trợ), hoặc tự kiểm tra loại ngoại lệ. `VerifyError` và `LinkageError` là `Error` vì JVM đang xử lý định nghĩa/liên kết class; không nên catch `Exception` chung rồi kết luận nhầm là lỗi dữ liệu.

`defineHiddenClass` tạo và **liên kết** class; một số tham chiếu, chỉ dẫn và khởi tạo có thể bị kiểm tra/giải quyết muộn hơn khi mã được chạy. Do đó test không chỉ cần “define thành công” mà còn cần thực thi các phương thức thực sự dùng của hidden class. Nếu `initialize=true` và static initializer lỗi, có thể quan sát `ExceptionInInitializerError`; đó là vấn đề khởi tạo, khác với `ClassFormatError`.

Đừng viết test cứng theo chuỗi message nội bộ của HotSpot cho các lỗi này: **kiểu ngoại lệ** và điều kiện kích hoạt quan trọng hơn thông báo có thể thay đổi theo JVM/vendor/version.

## 6. Tích hợp JUnit: tách từng nhánh thành test độc lập

Sau khi có ba file ví dụ ở mục 4, có thể thêm class test sau trong **`src/test/java/demo/hidden/HiddenClassContractTest.java`**, với JUnit Jupiter và build tool đã cấu hình. Đây là **class test thuộc dự án JUnit**, không chạy trực tiếp bằng lệnh `java`.

~~~java
package demo.hidden;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.lang.invoke.MethodHandles;
import org.junit.jupiter.api.Test;

class HiddenClassContractTest {
    @Test
    void samePackageProducesHiddenClass() throws Exception {
        byte[] bytes = HiddenLab.classBytes(
                "demo/hidden/Template.class");
        Class<?> hidden = MethodHandles.lookup()
                .defineHiddenClass(bytes, false)
                .lookupClass();

        assertTrue(hidden.isHidden());
        assertEquals("demo.hidden", hidden.getPackageName());
    }

    @Test
    void differentPackageIsRejected() throws IOException {
        byte[] bytes = HiddenLab.classBytes(
                "demo/other/ForeignTemplate.class");

        assertThrows(IllegalArgumentException.class, () ->
                MethodHandles.lookup().defineHiddenClass(bytes, false));
    }

    @Test
    void publicLookupCannotDefineHiddenClass() throws IOException {
        byte[] bytes = HiddenLab.classBytes(
                "demo/hidden/Template.class");

        assertThrows(IllegalAccessException.class, () ->
                MethodHandles.publicLookup()
                        .defineHiddenClass(bytes, false));
    }

    @Test
    void malformedClassFileIsRejected() {
        byte[] bytes = {0, 1, 2, 3};

        assertThrows(ClassFormatError.class, () ->
                MethodHandles.lookup().defineHiddenClass(bytes, false));
    }
}
~~~

Để test có ý nghĩa:

1. Dùng **cùng runtime JDK** mà sản phẩm thật sự hỗ trợ và dùng test runner hỗ trợ JDK đó; với ví dụ `--release 17`, JDK chạy phải là Java 17+.
2. Tách fixture `Template.class`, `ForeignTemplate.class` và byte array hỏng; chỉ thay **một điều kiện** mỗi lần để lỗi có tính chẩn đoán.
3. Kiểm tra **ca thành công và các nhánh thất bại**, tránh chỉ assert `isHidden()`. Riêng `NESTMATE`, kiểm tra cả trường hợp bị từ chối khi không có tùy chọn và được cấp quyền khi có nó.
4. Không viết test giả định tên hidden class có hậu tố cố định; có thể kiểm tra `isHidden()`, `getPackageName()` và việc `Class.forName` không tìm thấy.
5. Khi kiểm thử lỗi class-file version hoặc verifier, sinh fixture có kiểm soát bằng assembler/generator bytecode đáng tin cậy, lưu bản đã sinh cùng cấu hình version và test trên đúng JDK. Không tạo fixture bằng cách sửa byte header ngẫu nhiên rồi suy luận nó chỉ gây một lỗi nhất định.

Test framework thường có phép `assertThrows` cho các lỗi JVM (có thể truyền `ClassFormatError.class` hoặc `VerifyError.class`). Nó xác minh một ngoại lệ cùng kiểu hoặc kiểu con; nếu muốn phân biệt chính xác giữa các subclass, dùng phương thức assert đúng loại mà phiên bản framework hỗ trợ.

## 7. Lưu ý khi viết mã sinh lớp ẩn trong dự án thực tế

**Không nhầm quyền với package:** nếu đầu vào là `demo.other.ForeignTemplate.class`, việc đổi `publicLookup()` sang lookup đặc quyền chỉ giải quyết vấn đề quyền; nó không khiến `this_class` chuyển sang `demo.hidden`. Ngược lại, bytecode có package đúng vẫn thất bại nếu lookup thiếu full privilege.

**Không dùng hidden class để chia sẻ API công khai theo tên:** một bên thứ ba không thể khai báo `extends SomeHidden`, field hoặc parameter type trỏ đến tên hidden class bằng constant pool thông thường. Nếu muốn API ổn định/tra cứu bằng tên, cân nhắc class thông thường hoặc interface công khai mà hidden class triển khai, và truyền đối tượng/method handle hợp lệ.

**Không dựa vào đường dẫn file để đánh giá package:** compiler hoặc generator ghi `this_class` bên trong bytecode; đọc file từ `demo/hidden` nhưng bytecode thực tế ghi `demo/other` vẫn bị từ chối.

**Không trao toàn bộ quyền cho dữ liệu không tin cậy:** `Lookup` full privilege và `NESTMATE` là những năng lực nhạy cảm. Xác thực nguồn bytecode, giới hạn điểm cấp lookup và phạm vi module; class verification bảo vệ tính hợp lệ của chương trình JVM, không phải ranh giới an toàn cho mã độc.

**Không áp dụng cách làm đã bị thay thế:** tránh các đường tạo anonymous class nội bộ/không được hỗ trợ của `sun.misc.Unsafe`. Với nhu cầu lớp ẩn hiện nay, dùng `Lookup.defineHiddenClass` hoặc `defineHiddenClassWithClassData` (API từ Java 16 khi cần gắn class data) và các cơ chế module/lookup chính thức.

**Không ghi đè bằng ngoại lệ quá rộng:** `IllegalArgumentException` báo sai package/loại class; `IllegalAccessException` báo thiếu quyền; `ClassFormatError` báo sai cấu trúc bytecode; `VerifyError` báo sai ràng buộc bytecode. Log ngữ cảnh có ích gồm lookup class, module, package mong đợi, nguồn tạo bytecode và class-file version, nhưng không tiết lộ payload hoặc nội dung nhạy cảm.

## 8. Checklist kiểm thử trước khi đánh dấu PASS

- [ ] Dùng `MethodHandles.lookup()` ở đúng lớp/module có thẩm quyền; `lookup.hasFullPrivilegeAccess()` đúng khi định nghĩa.
- [ ] Bytecode hợp lệ, phiên bản class file được JVM mục tiêu hỗ trợ, `this_class` thuộc đúng package của lookup class.
- [ ] Test xác nhận `hidden.isHidden()`, `hidden.getPackageName()` và không phụ thuộc suffix của `hidden.getName()`.
- [ ] Test phương thức `package-private` hoạt động khi cùng runtime package; test `private` phân biệt rõ có/không có `NESTMATE`.
- [ ] Test lookup thiếu quyền -> `IllegalAccessException`; khác package -> `IllegalArgumentException`; bytes hỏng -> `ClassFormatError`.
- [ ] Với generator bytecode, test thêm version, verifier, lỗi liên kết, khởi tạo khi phù hợp; cả lúc tạo lẫn lúc thực thi mã.
- [ ] Không dùng `Class.forName` hoặc `ClassLoader.loadClass` để truy xuất hidden class; sử dụng `Class`, `Lookup` hoặc `MethodHandle` đã giữ.
- [ ] Chạy bộ test bằng JDK thực tế mà ứng dụng hỗ trợ, bao gồm module boundaries và class loader tương ứng trong môi trường triển khai.

Khi ba nhánh **khác package**, **thiếu lookup privilege** và **class file sai cấu trúc** được kiểm thử độc lập, kết quả lỗi mang ý nghĩa rõ ràng. Khi ca cùng package, quyền package-private và tùy chọn `NESTMATE` hoạt động đúng, mới có cơ sở xác nhận cách dùng hidden class hợp lệ trên JDK mục tiêu.

## Tài liệu chính thức

- [Java SE 25 – MethodHandles.Lookup.defineHiddenClass, đặc quyền, package, NESTMATE và ngoại lệ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...))
- [Java SE 25 – MethodHandles.Lookup và kiểm tra quyền theo module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 25 – Class.isHidden()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#isHidden())
- [Java Virtual Machine Specification – The class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html)
- [Java Virtual Machine Specification – Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html)
- [OpenJDK JEP 371 – Hidden Classes (Java 15)](https://openjdk.org/jeps/371)
