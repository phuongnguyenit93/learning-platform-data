# Giới hạn của `--illegal-access` trong Java hiện đại

## 1. Vấn đề mà `--illegal-access` từng giải quyết

Trước Java 9, nhiều thư viện dùng Reflection để mở những field, method, constructor nội bộ của JDK, ví dụ gọi `setAccessible(true)` đối với member không public trong các package thuộc `java.base`. Cách này dựa vào chi tiết triển khai, dễ bị phá vỡ khi JDK cập nhật. Kể từ Java 9, **Java Platform Module System (JPMS)** đưa ra quy tắc đóng gói mạnh (*strong encapsulation*): mỗi module quyết định package nào được `exports` (truy cập công khai) và package nào được `opens` (cho phép deep reflection).

`--illegal-access` là tùy chọn khởi chạy JVM được đưa vào để hỗ trợ chuyển đổi ứng dụng cũ sử dụng **illegal reflective access vào các package của JDK từng có trong Java 8**. Nó không phải công tắc vô hiệu hóa mọi quy tắc truy cập Java, không tạo quyền truy cập cho toàn bộ ứng dụng/modular library tùy ý và không hợp thức hóa mã dùng API nội bộ.

**Điểm phải nhớ với Java hiện đại: kể từ JDK 17, `--illegal-access=permit`, `warn`, `debug` và `deny` đều không còn tác dụng cấp quyền.** Trong các JDK hiện hành còn chấp nhận cú pháp này, JVM chỉ cảnh báo tùy chọn đã lỗi thời/bị bỏ qua. Không thể dùng `--illegal-access=permit` để chữa `InaccessibleObjectException` trên JDK 17+.

## 2. Dòng thời gian: Java 8 → 9–15 → 16 → 17+

| Phiên bản | Trạng thái đóng gói JDK và `--illegal-access` | Hệ quả thực tế |
| --- | --- | --- |
| Java 8 và cũ hơn | Chưa có JPMS hay tùy chọn `--illegal-access`. | Reflection vẫn chịu kiểm tra quyền truy cập Java và các giới hạn khác; một số thư viện truy cập được chi tiết JDK nội bộ. |
| JDK 9–15 | JPMS được giới thiệu; chế độ mặc định tương đương `--illegal-access=permit` đối với nhiều package JDK đã tồn tại từ Java 8. | Cho phép một số truy cập Reflection cũ trong giai đoạn chuyển tiếp; lần truy cập bất hợp lệ đầu tiên được cảnh báo trong chế độ permit. |
| JDK 16 | JEP 396 đổi mặc định thành `--illegal-access=deny`, bật strong encapsulation theo mặc định. | `--illegal-access=permit` vẫn có thể tạm khôi phục quyền truy cập tương thích trước đó cho phạm vi mà tùy chọn hỗ trợ. |
| JDK 17 trở lên | JEP 403 biến `--illegal-access` thành tùy chọn **obsolete/ignored**. | Các giá trị `permit`/`warn`/`debug`/`deny` không nới hoặc siết thêm quyền; muốn deep reflection phải mở rõ package phù hợp bằng cơ chế JPMS. |

Trong giai đoạn JDK 9–16, các chế độ lịch sử là:

- `permit`: nới quyền Reflection theo phạm vi tương thích cũ; cảnh báo lần đầu.
- `warn`: tương tự về việc cho phép, nhưng cảnh báo cho từng truy cập bất hợp lệ.
- `debug`: như `warn`, kèm stack trace nhằm tìm caller.
- `deny`: không nới quyền; truy cập vẫn có thể được phép bởi những cấu hình tường minh khác như `--add-opens`.

Các cờ trên **không áp dụng chung cho mọi module do lập trình viên tạo**. Đặc biệt, trên JDK 17+, viết `--illegal-access=deny` cũng không phải cách khóa mọi sự mở quyền đang có: JVM bỏ qua tùy chọn này; các `--add-opens` cụ thể vẫn quyết định quyền truy cập được thêm vào.

## 3. Vì sao `setAccessible(true)` không còn vượt được mọi rào cản?

Reflection có thể tìm ra một member nhưng chưa chắc có quyền đọc hoặc gọi member đó. Cần phân biệt:

1. `getDeclaredMethod()`, `getDeclaredField()`, `getDeclaredConstructor()`: **lấy metadata** về member có khai báo trong kiểu, kể cả private. Việc lấy metadata không tự cấp quyền sử dụng.
2. `setAccessible(true)`: yêu cầu bỏ qua một phần kiểm tra truy cập thông thường cho member, **chỉ thành công khi JPMS cho phép**. Nếu package của named module không mở cho module gọi và điều kiện khác không thỏa, có thể ném `java.lang.reflect.InaccessibleObjectException`.
3. `trySetAccessible()`: phiên bản thuận tiện trả `false` khi không thể cho phép truy cập, thay vì `InaccessibleObjectException` trong trường hợp không có quyền; vẫn cần xử lý ngoại lệ liên quan nếu có.
4. `Method.invoke()`, `Field.get()` hoặc constructor invocation: thực sự dùng member. Nếu chưa được phép, các API này có thể ném `IllegalAccessException` (khác với ngoại lệ khi yêu cầu bật quyền).

Ngay cả một public class trong package **đã `exports`** cũng không tự mở private member cho ứng dụng khác. `exports` và `opens` có tác dụng khác nhau:

| Cấu hình | Truy cập public type/member bằng Java thông thường | Deep reflection vào private member từ module khác |
| --- | --- | --- |
| Package `exports` đến module gọi | Được phép, nếu các điều kiện truy cập Java khác cũng thỏa. | Không tự động được phép. |
| Package `opens` đến module gọi | Không tự động cho phép code khác compile tham chiếu public type khi package không `exports`. | Được phép yêu cầu `setAccessible(true)` trong những điều kiện JPMS thích hợp. |
| `exports` và `opens` | Cho phép cả truy cập public thông thường và deep reflection thuộc phạm vi đã cấp. | Có thể hoạt động. |
| Package không export/open cho caller | Không được truy cập thông thường từ caller. | Bị từ chối deep reflection. |

## 4. Ví dụ Java 17+: lỗi thật và cách mở đúng một package

Ví dụ dưới dùng **module tự tạo**, không phụ thuộc field nội bộ của `String` hay lớp nội bộ JDK có thể thay đổi. Module `demo.lib` cho phép lớp ngoài nhìn thấy `Greeter` qua `exports demo.api`, nhưng chưa cho phép truy cập deep reflection tới `private secret()`.

Tạo cấu trúc thư mục:

~~~text
project/
├── src/
│   └── demo.lib/
│       ├── module-info.java
│       └── demo/
│           └── api/
│               └── Greeter.java
└── Main.java
~~~

**Tệp `src/demo.lib/module-info.java`:**

~~~java
module demo.lib {
    exports demo.api;
}
~~~

**Tệp `src/demo.lib/demo/api/Greeter.java`:**

~~~java
package demo.api;

public class Greeter {
    private String secret() {
        return "hello";
    }
}
~~~

**Tệp `Main.java`:** chương trình nằm trên class path, tức thuộc *unnamed module*.

~~~java
import demo.api.Greeter;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws Exception {
        Method method = Greeter.class.getDeclaredMethod("secret");

        try {
            method.setAccessible(true);
            System.out.println("result=" + method.invoke(new Greeter()));
        } catch (InaccessibleObjectException e) {
            System.out.println("blocked=" + e.getClass().getSimpleName());
        }
    }
}
~~~

Đứng tại thư mục `project`, biên dịch với JDK 17+:

~~~bash
javac --release 17 -d mods --module-source-path src -m demo.lib
javac --release 17 --module-path mods --add-modules demo.lib -d classes Main.java
~~~

### Chạy 1: không mở package

~~~bash
java --module-path mods --add-modules demo.lib -cp classes Main
~~~

Stdout:

~~~text
blocked=InaccessibleObjectException
~~~

`getDeclaredMethod("secret")` đã tìm được method nhưng `setAccessible(true)` không có quyền mở private member. Vì vậy không in ra `hello`.

### Chạy 2: thêm `--illegal-access=permit`

~~~bash
java --illegal-access=permit --module-path mods --add-modules demo.lib -cp classes Main
~~~

Stdout vẫn là:

~~~text
blocked=InaccessibleObjectException
~~~

Trên OpenJDK 24, JVM còn phát cảnh báo ra stderr, chẳng hạn:

~~~text
OpenJDK 64-Bit Server VM warning: Ignoring option --illegal-access=permit; support was removed in 17.0
~~~

Dòng cảnh báo, định dạng và việc tương lai JVM có chấp nhận cú pháp cũ nữa hay không phụ thuộc phiên bản. **Điểm học tập là kết quả truy cập không thay đổi.** Đồng thời, `--illegal-access` lịch sử vốn không phải cơ chế mở tùy ý module ứng dụng như `demo.lib`.

### Chạy 3: cấp quyền đúng package và đúng caller

~~~bash
java --add-opens demo.lib/demo.api=ALL-UNNAMED --module-path mods --add-modules demo.lib -cp classes Main
~~~

Stdout:

~~~text
result=hello
~~~

`--add-opens demo.lib/demo.api=ALL-UNNAMED` mở package `demo.api` thuộc module `demo.lib` cho các unnamed module (thường là code trên class path). Khi ấy `setAccessible(true)` thành công.

**Kết luận từ ví dụ:** với nhu cầu deep reflection, quyền được thêm theo **module/package/caller**, không phải một cờ toàn cục `--illegal-access`. Cả ba lệnh và kết quả ở trên đã được kiểm tra với mã Java 17 tương thích.

## 5. Cấu hình thay thế đúng mục đích

### `--add-opens`: cho phép deep reflection

Cú pháp runtime:

~~~text
--add-opens <module-nguồn>/<package>=<module-đích>
~~~

Ví dụ cho code trên class path truy cập private member thuộc `java.lang`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp classes Main
~~~

Dòng này chỉ minh họa **cú pháp mở một package của JDK**, không phải lệnh chạy cho module `demo.lib` trong phần 4. Ví dụ phần 4 cần `--add-opens demo.lib/demo.api=ALL-UNNAMED`. Không có cơ sở để mở mọi package `java.base` chỉ vì một thư viện báo lỗi với một package cụ thể.

Nếu caller là **named module**, thay `ALL-UNNAMED` bằng tên module gọi, ví dụ:

~~~text
--add-opens demo.lib/demo.api=app.consumer
~~~

`--add-opens` thường là biện pháp tương thích tạm thời cho thư viện cũ; chọn package thực sự cần mở theo thông báo lỗi và tài liệu của thư viện. Quyền này cho phép caller có khả năng vượt kiểm tra truy cập thông thường với các member thuộc package đó.

### `--add-exports`: cho phép sử dụng public API của package chưa export

Cú pháp:

~~~text
--add-exports <module-nguồn>/<package>=<module-đích>
~~~

Dùng khi thư viện/ứng dụng cần dùng **public type và public member** của package chưa được export. Có thể cần cờ ở cả lúc biên dịch và lúc chạy. `--add-exports` không tương đương với cho phép deep reflection tới private member; trường hợp đó thường cần `--add-opens`.

### Khai báo chính thức trong `module-info.java`

Nếu **sở hữu** module thư viện và chủ động quyết định API, có thể khai báo:

~~~java
module demo.lib {
    exports demo.api;              // Cho code ngoài dùng public API
    opens demo.api to app.consumer; // Chỉ cho named module app.consumer deep reflection
}
~~~

Đây là ví dụ cấu hình cho tình huống **có module `app.consumer`**; đừng thay trực tiếp vào dự án class path ở phần 4 nếu chưa có module đó. Có thể khai báo `opens demo.api;` để mở package cho mọi module, nhưng nên chọn phạm vi hẹp phù hợp với kiến trúc. `open module ...` mở tất cả package của module cho reflection, thường rộng hơn nhu cầu thực tế.

Trong ứng dụng sử dụng framework, tốt nhất cấu hình `opens` (hoặc `opens ... to ...`) tại module mà mình kiểm soát, theo đúng tài liệu framework. Nếu vấn đề nằm ở internals của **JDK**, lập trình viên không sửa được `java.base/module-info.java` để thêm `opens`; phải dùng API công khai, cập nhật thư viện hoặc khai báo cờ runtime hẹp.

### `--add-reads` không thay thế `--add-opens`

`--add-reads` thay đổi quan hệ **readability** giữa module; nó không mở private member của package. Khi debug `InaccessibleObjectException`, thêm `--add-reads` không tự giải quyết thiếu quyền deep reflection.

## 6. Chẩn đoán lỗi khi nâng từ Java 8/11 lên Java 17+

Thông báo điển hình:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible: module java.base
does not "opens java.lang" to unnamed module ...
~~~

Văn bản chính xác có thể khác giữa JDK và member. Những phần cần xác định là:

1. **Module nguồn:** ví dụ `java.base`.
2. **Package bị đóng:** ví dụ `java.lang`.
3. **Caller cần quyền:** ví dụ `unnamed module` cho class path hoặc tên một named module.
4. **Tác vụ truy cập:** deep reflection vào non-public member hay tham chiếu thông thường tới public API trong package không export?

Nếu thật sự cần deep reflection và không thể chuyển sang API hỗ trợ chính thức, một tùy chọn thử có phạm vi hẹp là:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Đây là **ví dụ được suy ra từ thông báo giả định nêu trên**, không phải lời khuyên thêm cờ đó cho mọi dự án.

Quy trình xử lý hợp lý:

- **Xác định thư viện gọi Reflection:** đọc stack trace và phụ thuộc liên quan. Có thể chính thư viện serialize, dependency injection, ORM, bytecode proxy, mocking hoặc công cụ kiểm thử đang truy cập JDK internals.
- **Ưu tiên cập nhật dependency:** bản mới thường đã dùng API Java được hỗ trợ hoặc cơ chế phù hợp với JPMS. Tránh tự duy trì danh sách dài `--add-opens` nếu còn giải pháp đúng cấp API.
- **Nếu module là do mình viết:** chỉnh `module-info.java` theo đúng phạm vi `exports` hoặc `opens` cần thiết.
- **Nếu buộc mở package runtime:** chỉ thêm từng `--add-opens` được chứng minh cần thiết, đặt vào cấu hình JVM chạy chương trình và môi trường test thực sự. Cấu hình cho một tiến trình `java` không tự động áp dụng cho tiến trình JVM khác do công cụ build tạo.
- **Chạy lại trên phiên bản JDK triển khai thực tế:** có thể có thêm lỗi khi code chạm tới package khác. Không kết luận một cờ là đủ cho mọi môi trường từ một stack trace duy nhất.

Cách nhanh để xác định Java runtime đang chạy:

~~~bash
java -version
~~~

Nếu lệnh test/IDE/production dùng JDK khác với terminal, cần xác minh JVM **thực sự khởi chạy ứng dụng**. Đừng dựa vào `javac -version` của một terminal để kết luận toàn bộ hệ thống đã sử dụng cùng runtime.

## 7. Những hiểu lầm quan trọng

| Nhận định sai | Sửa cho đúng |
| --- | --- |
| “Thêm `--illegal-access=permit` là đủ khi nâng lên JDK 17+.” | Cờ đã obsolete và bị bỏ qua từ JDK 17. |
| “`--illegal-access=deny` vẫn đang chặn quyền trên JDK mới.” | Trạng thái quyền trên JDK 17+ không do cờ này quyết định; các tùy chọn cụ thể khác vẫn có tác dụng. |
| “`setAccessible(true)` luôn bỏ qua private bất kể module.” | JPMS có thể từ chối với `InaccessibleObjectException`. |
| “`getDeclaredField()` tìm được field nghĩa là đọc được.” | Khả năng nhìn metadata khác với quyền truy cập giá trị. |
| “`--add-exports` và `--add-opens` giống nhau.” | `exports` liên quan truy cập public API; `opens` hỗ trợ deep reflection. |
| “`ALL-UNNAMED` cho phép một named module gọi.” | `ALL-UNNAMED` nhắm tới code thuộc unnamed modules, thường là class path. |
| “Mở toàn bộ JDK internals là cách sửa bền vững.” | Dùng API chính thức, thư viện tương thích và chỉ mở package cụ thể khi cần. |
| “Mọi lỗi `IllegalAccessException` đều do `--illegal-access`.” | Có thể liên quan Java visibility, module readability, package export/open, caller hoặc đường gọi cụ thể; cần đọc ngoại lệ và stack trace. |

**Ngoại lệ lịch sử cần hiểu đúng:** JEP 403 vẫn cho phép một số API nội bộ quan trọng như `sun.misc.Unsafe` tiếp tục tồn tại theo cơ chế đặc biệt. Điều đó không có nghĩa toàn bộ JDK internals được mở, cũng không biến API không chuẩn thành hợp đồng ổn định.

## 8. Tự kiểm tra

1. Trên JDK 17+, chạy ba lệnh trong phần 4. Giải thích tại sao `Greeter.class.getDeclaredMethod("secret")` thành công nhưng `method.setAccessible(true)` bị từ chối trước khi mở package.
2. Thay `setAccessible(true)` bằng `System.out.println(method.trySetAccessible());`. Dự đoán `false` khi thiếu quyền và `true` khi có `--add-opens`; nhớ bỏ dòng `invoke` hoặc xử lý riêng nếu chỉ muốn thử khả năng mở.
3. Tại sao `exports demo.api` không cho truy cập private method? Nếu caller chuyển thành named module `app.consumer`, cần thay mục tiêu `ALL-UNNAMED` bằng gì?
4. Nếu thư viện chỉ cần public type của package chưa export, nên đánh giá `--add-exports` hay `--add-opens` trước? Nếu cần deep reflection vào private field thì chọn gì?
5. Trên JDK 17+, nếu ứng dụng cũ chạy với `--illegal-access=warn`, cảnh báo cũ có còn đóng vai trò công cụ phát hiện từng truy cập nữa không? Tại sao?

## Tài liệu chính thức

- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [JEP 396 — Strongly Encapsulate JDK Internals by Default (JDK 16)](https://openjdk.org/jeps/396)
- [JEP 403 — Strongly Encapsulate JDK Internals (JDK 17)](https://openjdk.org/jeps/403)
- [Oracle JDK 24 Migration Guide — Strong Encapsulation in the JDK](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Oracle Java Launcher Reference — `--add-opens`, `--add-exports`, obsolete options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Java SE 17 API — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
