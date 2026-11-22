# Phát hiện sử dụng API nội bộ bằng --jdk-internals

Java cung cấp các API công khai có hợp đồng tương thích được tài liệu hóa. Bên cạnh đó, JDK còn chứa các lớp và package nội bộ phục vụ việc triển khai runtime. Những API nội bộ có thể thay đổi hoặc bị loại bỏ giữa các phiên bản JDK, vì vậy ứng dụng phụ thuộc vào chúng có nguy cơ hỏng khi nâng cấp Java.

Công cụ **jdeps** đi kèm JDK có tùy chọn **--jdk-internals** để tìm các phụ thuộc ở cấp class vào API nội bộ của JDK trong file class, thư mục bytecode hoặc JAR. Đây là bước kiểm tra hữu ích khi nâng cấp JDK, chuyển ứng dụng sang JPMS hoặc rà soát dependency bên thứ ba.

Tùy chọn này phân tích bytecode đã biên dịch. Nó không phải cờ của **javac** hay **java**, không tự sửa mã nguồn và cũng không ngăn chương trình sử dụng API nội bộ. Kết quả cần được dùng để xác định nơi phụ thuộc, đánh giá rủi ro và thay thế bằng API công khai phù hợp.

## 1. API nội bộ của JDK là gì?

API nội bộ là các lớp, interface, method hoặc package thuộc chi tiết triển khai của JDK, không được cam kết là API công khai ổn định cho ứng dụng bên ngoài.

Các tên package thường gặp trong mã cũ gồm:

- **sun.***, ví dụ **sun.misc.Unsafe**.
- **com.sun.*** trong một số package triển khai nội bộ.
- **jdk.internal.***, chứa nhiều thành phần nội bộ của runtime và các module JDK.

Không nên kết luận chỉ dựa vào tiền tố package. Một số package có tên **com.sun** được cung cấp như API nền tảng có tài liệu chính thức, chẳng hạn **com.sun.net.httpserver** trong module **jdk.httpserver**. Hãy dựa vào phân tích của **jdeps --jdk-internals** và tài liệu JDK để xác định API cụ thể có phải internal API hay không.

Khác biệt quan trọng là hợp đồng hỗ trợ:

| Loại API | Hợp đồng sử dụng |
|---|---|
| API Java SE được tài liệu hóa | Có đặc tả/API documentation và chính sách tương thích theo phiên bản |
| API mở rộng JDK được tài liệu hóa riêng | Có thể có phạm vi hỗ trợ riêng, cần kiểm tra tài liệu của module/nhà cung cấp |
| JDK internal API | Chi tiết triển khai; có thể đổi tên, đổi hành vi, bị đóng gói hoặc bị loại bỏ mà không bảo đảm tương thích cho ứng dụng |

Việc một internal API hiện vẫn truy cập được không có nghĩa ứng dụng nên phụ thuộc vào nó. Ví dụ **sun.misc.Unsafe** được giữ lại cho một số nhu cầu tương thích quan trọng thông qua module **jdk.unsupported**, nhưng vẫn được **jdeps** nhận diện là JDK internal API.

## 2. --jdk-internals là tùy chọn của công cụ nào?

**--jdk-internals** là tùy chọn của công cụ phân tích phụ thuộc **jdeps** trong JDK. Nó tìm các phụ thuộc ở cấp class vào JDK internal APIs và hiển thị module chứa API được tham chiếu.

Lệnh cơ bản:

~~~bash
jdeps --jdk-internals path/to/application.jar
~~~

Đối tượng đầu vào có thể là:

- Một file **.class**.
- Một thư mục chứa các file class đã biên dịch.
- Một file JAR.

Ví dụ quét thư mục bytecode:

~~~bash
jdeps --jdk-internals out/
~~~

Ví dụ quét JAR:

~~~bash
jdeps --jdk-internals application.jar
~~~

Có thể kiểm tra phiên bản công cụ:

~~~bash
jdeps --version
~~~

Nên dùng **jdeps** thuộc đúng JDK mục tiêu hoặc JDK mới hơn mà dự án hỗ trợ. Kết quả phụ thuộc vào phiên bản JDK và tập module hệ thống mà công cụ sử dụng để nhận diện internal APIs.

Đừng nhầm các lệnh sau:

| Lệnh/công cụ | Vai trò |
|---|---|
| **javac** | Biên dịch mã nguồn Java thành bytecode |
| **java** | Khởi chạy ứng dụng |
| **jdeps --jdk-internals** | Phân tích bytecode để tìm phụ thuộc vào JDK internal APIs |
| **jdeprscan** | Quét việc sử dụng các API đã deprecated theo cơ sở dữ liệu phiên bản JDK |

**--jdk-internals** không phải tùy chọn chạy ứng dụng và không cấp quyền truy cập vào package nội bộ.

## 3. Cách đọc kết quả phân tích

Khi tìm thấy internal API, **jdeps** thường hiển thị module nguồn, class phụ thuộc, tên API và module JDK sở hữu API đó.

Ví dụ kết quả đã kiểm tra trên JDK 24.0.2:

~~~text
legacy-allocator.jar -> jdk.unsupported
   legacy.LegacyAllocator -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation that are
subject to be removed or changed incompatibly and could break your application.

JDK Internal API                         Suggested Replacement
----------------                         ---------------------
sun.misc.Unsafe                          See https://openjdk.org/jeps/260
~~~

Cách đọc:

- **legacy-allocator.jar** là artifact đang được phân tích.
- **legacy.LegacyAllocator** là class của ứng dụng có tham chiếu.
- **sun.misc.Unsafe** là API nội bộ được sử dụng.
- **jdk.unsupported** là module JDK chứa API này.
- Phần **Suggested Replacement** cung cấp hướng tham khảo nếu JDK có đề xuất thay thế.

Kết quả này giúp truy ngược từ API nội bộ về class hoặc dependency đang dùng nó. Nếu class thuộc thư viện bên thứ ba, cần xác định phiên bản thư viện và tìm bản cập nhật đã loại bỏ phụ thuộc đó.

Bảng thay thế không phải công cụ tự chuyển đổi mã. Một số API có đề xuất cụ thể, một số trường hợp chỉ dẫn tới tài liệu tổng quan; nhóm phát triển vẫn cần chọn thiết kế thay thế phù hợp với hành vi mà ứng dụng thực sự cần.

## 4. Ví dụ hoàn chỉnh: quét JAR có sử dụng sun.misc.Unsafe

Ví dụ sau mô phỏng một thư viện cũ dùng **sun.misc.Unsafe** để cấp phát object mà không gọi constructor. Đây là cách phụ thuộc vào chi tiết triển khai và không nên dùng trong mã ứng dụng mới.

Cấu trúc:

~~~text
project/
  src/
    legacy/
      LegacyAllocator.java
  out/
  legacy-allocator.jar
~~~

**Tệp src/legacy/LegacyAllocator.java:**

~~~java
package legacy;

import sun.misc.Unsafe;

public final class LegacyAllocator {
    private static final Unsafe UNSAFE;

    static {
        try {
            var field = Unsafe.class.getDeclaredField("theUnsafe");
            field.setAccessible(true);
            UNSAFE = (Unsafe) field.get(null);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private LegacyAllocator() {
    }

    public static Object allocate(Class<?> type) throws InstantiationException {
        return UNSAFE.allocateInstance(type);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out src/legacy/LegacyAllocator.java
~~~

Compiler có thể phát cảnh báo rằng **Unsafe** là proprietary/internal API và có thể bị loại bỏ trong bản phát hành tương lai. Cảnh báo biên dịch này là dấu hiệu hữu ích, nhưng chưa thay thế việc quét toàn bộ artifact và dependency.

Đóng gói JAR:

~~~bash
jar --create --file legacy-allocator.jar -C out .
~~~

Chạy phân tích:

~~~bash
jdeps --jdk-internals legacy-allocator.jar
~~~

Kết quả sẽ chỉ ra class **legacy.LegacyAllocator** phụ thuộc vào **sun.misc.Unsafe** trong module **jdk.unsupported**.

Ví dụ không cần gọi method **allocate** để jdeps phát hiện phụ thuộc. Chỉ cần bytecode có tham chiếu tới kiểu nội bộ, công cụ đã có thể báo cáo. Đây là phân tích phụ thuộc tĩnh, không phải kiểm thử hành vi runtime.

## 5. Quét thư mục, JAR và dependency đi kèm

Trong dự án thực tế, quét riêng JAR chính có thể bỏ sót internal API nằm trong thư viện phụ thuộc. Hãy đưa các dependency cần phân tích vào classpath hoặc module path để **jdeps** có thể phân giải và kiểm tra chúng.

Ví dụ khi ứng dụng dùng một thư viện JAR:

~~~bash
jdeps --jdk-internals --class-path lib/dependency.jar application.jar
~~~

Có thể chỉ định nhiều JAR trong classpath bằng dấu phân cách của hệ điều hành: dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS.

Nếu muốn phân tích cả dependency runtime theo chuỗi, cân nhắc tùy chọn **--recursive**. Tùy cấu trúc build, có thể cần cung cấp đầy đủ module path/classpath để công cụ tìm được các dependency. Hãy kiểm tra output để xác nhận đúng tập artifact đã được phân tích.

Một quy trình hữu ích:

1. Quét thư mục output sau khi biên dịch module ứng dụng.
2. Quét JAR chính đã đóng gói.
3. Quét các thư viện trực tiếp và gián tiếp có trong runtime.
4. Quét plugin hoặc extension được phân phối riêng nếu chúng chạy trong cùng sản phẩm.
5. Lưu kết quả theo từng phiên bản JDK mục tiêu để so sánh khi nâng cấp.

Không nên chỉ quét thư mục source. **jdeps** cần bytecode đã biên dịch để phân tích các tham chiếu class-level.

## 6. Quét multi-release JAR đúng phiên bản

Một multi-release JAR có thể chứa nhiều phiên bản class cho các mức Java khác nhau, thường nằm trong **META-INF/versions/**. Runtime chọn class phù hợp với phiên bản Java đang chạy.

Khi phân tích loại JAR này, chỉ định view cần kiểm tra bằng **--multi-release**:

~~~bash
jdeps --multi-release 17 --jdk-internals application.jar
~~~

Giá trị là phiên bản Java từ 9 trở lên hoặc **base**. Ví dụ trên yêu cầu jdeps phân tích nội dung multi-release tương ứng Java 17.

Nếu artifact hỗ trợ nhiều phiên bản runtime, hãy kiểm tra từng view có liên quan. Một nhánh class dành cho Java 17 có thể không giống nhánh dành cho Java 21 hoặc phiên bản cao hơn. Quét một view không tự chứng minh mọi nhánh còn lại đều không dùng internal API.

## 7. Giới hạn của phân tích tĩnh

**jdeps --jdk-internals** phân tích phụ thuộc ở cấp class trong bytecode. Nó rất hữu ích nhưng không quan sát được mọi cách chương trình có thể truy cập một API.

Có thể bỏ sót các trường hợp như:

- Tên class nội bộ chỉ xuất hiện dưới dạng chuỗi trong **Class.forName("...")**.
- Tên class được ghép động từ cấu hình hoặc dữ liệu bên ngoài.
- Framework nạp class qua reflection, plugin registry hoặc class loader tùy chỉnh mà không có tham chiếu bytecode trực tiếp.
- JNI hoặc mã native truy cập thành phần của runtime.
- Bytecode được sinh ra lúc chạy hoặc được tải từ nguồn không nằm trong tập artifact đã quét.
- Dependency hoặc plugin không được đưa vào classpath/module path của lần phân tích.

Vì vậy, kết quả không có dòng internal API chỉ có nghĩa là công cụ không tìm thấy phụ thuộc class-level trong tập đầu vào đã cung cấp. Nó không phải bằng chứng tuyệt đối rằng toàn bộ hệ thống không có bất kỳ truy cập động nào.

Kết hợp phân tích với tìm kiếm source cho các mẫu như **Class.forName**, **getDeclaredField**, **setAccessible**, **MethodHandles** và cơ chế nạp plugin. Những mẫu này không mặc nhiên là lỗi, nhưng cần kiểm tra xem tên hoặc thành viên nội bộ có bị truy cập động hay không.

## 8. Từ phát hiện đến thay thế API nội bộ

Khi **jdeps** báo một internal API, không nên thay thế chỉ dựa vào tên lớp. Trước tiên xác định chức năng thực tế mà ứng dụng đang sử dụng.

Một số hướng thay thế phổ biến:

| Nhu cầu hiện tại | API công khai nên xem xét |
|---|---|
| Truy cập field với thao tác volatile/atomic hoặc truy cập có kiểu | **java.lang.invoke.VarHandle** |
| Tạo method handle hoặc kiểm soát lookup | **java.lang.invoke.MethodHandles** |
| Làm việc với vùng dữ liệu byte | **java.nio.ByteBuffer** và các API buffer |
| Truy cập bộ nhớ native và tương tác native có kiểm soát trên JDK hiện đại | **java.lang.foreign** Foreign Function & Memory API |
| Cấp phát object mà không gọi constructor | Thiết kế lại vòng đời object bằng constructor, factory hoặc deserialization API được hỗ trợ |

Không phải mọi chức năng của **Unsafe** đều có một API thay thế một-một. Ví dụ, nếu ứng dụng dùng **allocateInstance** để bỏ qua constructor, hãy xem lại lý do thiết kế cần hành vi này. Có thể cần chuyển sang factory, constructor phù hợp hoặc một quy trình khởi tạo/deserialization được hỗ trợ.

Ví dụ dùng **VarHandle** cho cập nhật field nguyên tử:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile int value;
    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public int increment() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }

    public static void main(String[] args) {
        Counter counter = new Counter();
        System.out.println(counter.increment());
        System.out.println(counter.increment());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -d out Counter.java
java -cp out Counter
~~~

Output:

~~~text
1
2
~~~

Đây là ví dụ cho một nhu cầu truy cập field nguyên tử. **VarHandle** không phải giải pháp thay thế cho mọi khả năng cấp phát hoặc thao tác bộ nhớ của **Unsafe**.

## 9. Strong encapsulation trên JDK hiện đại

JPMS được giới thiệu từ Java 9. JEP 260 xác định chiến lược đóng gói phần lớn internal APIs và đưa ra hướng thay thế. JEP 403 tăng cường strong encapsulation của JDK internals từ Java 17.

Một số API quan trọng vì lý do tương thích vẫn có thể được cung cấp qua module như **jdk.unsupported**. Điều này không biến chúng thành API Java SE ổn định. **sun.misc.Unsafe** là ví dụ: có thể vẫn truy cập được trong một số cấu hình JDK, nhưng vẫn bị **jdeps --jdk-internals** cảnh báo là internal API.

Khi nâng cấp JDK:

1. Chạy lại **jdeps --jdk-internals** trên artifact và dependency.
2. Đọc cảnh báo compile/runtime liên quan đến internal API.
3. Kiểm tra JEP hoặc tài liệu JDK về API cụ thể và replacement.
4. Nâng cấp dependency bên thứ ba nếu nhà cung cấp đã loại bỏ internal API.
5. Thay code nội bộ của ứng dụng bằng API công khai phù hợp.
6. Chạy lại test trên phiên bản JDK mục tiêu và kiểm tra các luồng reflection/dynamic loading riêng.

Không dựa vào tùy chọn mở quyền module để biến internal API thành API được hỗ trợ lâu dài. **--add-exports** hoặc **--add-opens** có thể thay đổi quyền truy cập trong một số tình huống, nhưng không tạo cam kết tương thích cho chi tiết triển khai JDK.

## 10. Tích hợp vào quy trình build và CI

Nên đưa bước quét internal API vào quy trình kiểm tra artifact sau compile/package, đặc biệt trước khi nâng phiên bản JDK hoặc phát hành thư viện dùng lại ở nhiều ứng dụng.

Một pipeline có thể thực hiện:

~~~text
Compile
   |
   v
Package application and dependencies
   |
   v
Run jdeps --jdk-internals
   |
   v
Review reported classes and dependencies
   |
   v
Replace or update dependencies
   |
   v
Run tests on target JDK
~~~

Ví dụ các lệnh tối thiểu:

~~~bash
javac --release 17 -d out src/example/Main.java
jar --create --file application.jar -C out .
jdeps --jdk-internals application.jar
~~~

Nếu dự án có thư viện bên ngoài, bổ sung classpath/module path đúng với cấu hình runtime. Trong CI, lưu report để nhóm phát triển có thể theo dõi API mới xuất hiện sau mỗi lần cập nhật dependency.

**jdeps** là công cụ chẩn đoán; bản thân lệnh không tự chuyển mã và không phải cơ chế policy enforcement hoàn chỉnh. Nếu muốn pipeline thất bại khi phát hiện internal API, hãy xây dựng bước kiểm tra output có chủ đích, xử lý đúng mã thoát và phân biệt warning với lỗi chạy công cụ.

Có thể quản lý danh sách ngoại lệ tạm thời cho dependency chưa thể nâng cấp, nhưng mỗi ngoại lệ nên có chủ sở hữu, lý do, phiên bản dependency, phạm vi ảnh hưởng và thời điểm đánh giá lại. Không nên bỏ qua toàn bộ report chỉ vì một thư viện cũ chưa thể thay thế ngay.

## 11. Lỗi và hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| **jdeps** không tìm thấy class phụ thuộc | Thiếu classpath hoặc module path khi phân tích | Cung cấp dependency path phù hợp và chạy lại |
| Quét source không thấy kết quả | jdeps phân tích class/JAR đã biên dịch | Compile trước rồi quét thư mục output hoặc artifact |
| Có cảnh báo javac nhưng report jdeps khác | Compiler warning và phân tích bytecode có phạm vi khác nhau | Kiểm tra cả compile output và report jdeps |
| **sun.misc.Unsafe** vẫn chạy nhưng jdeps báo internal API | Một số internal API còn được giữ vì tương thích | Xem đây là phụ thuộc cần xử lý, không coi khả năng truy cập hiện tại là cam kết ổn định |
| Không có report nhưng ứng dụng vẫn dùng reflection nội bộ | Tham chiếu động không hiện thành class-level dependency | Rà soát reflection, cấu hình, plugin và native code |
| Multi-release JAR cho kết quả khác nhau | Mỗi phiên bản Java có thể chọn một class implementation khác | Chỉ định **--multi-release** cho từng runtime mục tiêu |
| Muốn lọc theo package bằng **-p** cùng lúc | **--jdk-internals** không kết hợp được với một số bộ lọc như **-p**, **-e**, **-s** | Chạy phân tích riêng hoặc lọc report ở bước xử lý sau |
| Nghĩ jdeps tự thay API | Tool chỉ báo cáo phụ thuộc và gợi ý | Đánh giá hành vi cần thiết rồi refactor/nâng cấp dependency |

## 12. Checklist trước khi phát hành

- [ ] Đã chạy **jdeps --jdk-internals** trên thư mục class hoặc JAR đã build.
- [ ] Đã đưa các dependency runtime cần kiểm tra vào classpath/module path.
- [ ] Đã quét plugin hoặc extension được phân phối riêng.
- [ ] Đã chọn đúng view **--multi-release** nếu artifact là multi-release JAR.
- [ ] Đã xác định class cụ thể và module JDK chứa internal API được báo cáo.
- [ ] Đã phân biệt API internal với API public có tên package dễ gây nhầm.
- [ ] Đã kiểm tra các đường truy cập động qua reflection, class loading và native code.
- [ ] Đã tìm replacement công khai hoặc phiên bản dependency đã sửa.
- [ ] Đã kiểm thử trên JDK mục tiêu, không chỉ dựa vào việc compile thành công.
- [ ] Đã ghi nhận ngoại lệ còn tồn tại và kế hoạch loại bỏ phụ thuộc.

## 13. Tài liệu tham khảo

- [Java SE 25 — jdeps tool reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html)
- [JEP 260 — Encapsulate Most Internal APIs](https://openjdk.org/jeps/260)
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [Java SE 25 API — VarHandle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java SE 25 API — MethodHandles](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 25 API — Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/package-summary.html)
