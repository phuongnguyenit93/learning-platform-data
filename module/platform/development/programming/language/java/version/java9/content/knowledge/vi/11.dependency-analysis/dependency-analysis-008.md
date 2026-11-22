# Đối chiếu kết quả phân tích tĩnh với kiểm thử lúc chạy

Trong dự án JPMS, phân tích tĩnh và kiểm thử lúc chạy trả lời hai nhóm câu hỏi khác nhau. Phân tích tĩnh cho biết bytecode và module descriptor khai báo hoặc tham chiếu những phụ thuộc nào. Kiểm thử lúc chạy cho biết JVM có phân giải được module graph, tìm được provider, nạp được lớp và thực thi đúng hành vi trong cấu hình triển khai hay không.

Hai kết quả cần được đối chiếu trước khi phát hành. Một đồ thị phụ thuộc tĩnh hợp lệ chưa chứng minh mọi luồng chạy đều hoạt động. Ngược lại, một bài kiểm thử chạy thành công cũng chưa chứng minh descriptor gọn, không có phụ thuộc thừa hoặc không tham chiếu API nội bộ của JDK.

Trong Java 9 trở lên, **jdeps** là công cụ chính để phân tích phụ thuộc bytecode và module descriptor. Các lệnh chạy Java, đặc biệt **--show-module-resolution**, cùng integration test giúp kiểm chứng đồ thị thực tế và hành vi ứng dụng.

## 1. Phân biệt phân tích tĩnh và kiểm thử lúc chạy

### 1.1. Phân tích tĩnh

Phân tích tĩnh xem xét artifact đã biên dịch và thông tin mô-đun mà không thực thi luồng nghiệp vụ. Với dự án modular, nó có thể giúp trả lời:

- Lớp trong mô-đun tham chiếu package hoặc kiểu nào?
- Mô-đun đang khai báo những quan hệ **requires** nào?
- Có phụ thuộc module nào bị thiếu trong phạm vi artifact và module path được cung cấp cho công cụ phân tích không?
- Module descriptor có khai báo phụ thuộc chưa cần thiết hoặc qualified export không được dùng không?
- Mô-đun có tham chiếu API nội bộ của JDK không?
- Có thể rút gọn danh sách module dependency để hỗ trợ đóng gói runtime image không?

Phân tích tĩnh hữu ích trong code review, CI và khi nâng cấp JDK hoặc thư viện. Nó giúp phát hiện vấn đề trước khi chạy ứng dụng.

### 1.2. Kiểm thử lúc chạy

Kiểm thử lúc chạy khởi động JVM bằng cấu hình triển khai thật hoặc gần với cấu hình đó. Nó kiểm tra những gì xảy ra khi JVM phân giải mô-đun, liên kết service, nạp lớp và gọi mã.

Các tình huống runtime cần quan tâm:

- Mô-đun có mặt trên module path và được phân giải đúng không?
- Provider được khai báo qua **provides ... with ...** có được tìm thấy không?
- Constructor hoặc provider method có khởi tạo thành công không?
- Reflection, cấu hình, tài nguyên và các lớp được nạp động có hoạt động không?
- Hành vi trả về có đúng với yêu cầu nghiệp vụ không?
- Ứng dụng có hoạt động trên đúng JDK, module path, JVM options và môi trường triển khai không?

Một chương trình chỉ chạy được trên classpath chưa chắc đã chạy đúng trên module path. Hãy chạy integration test theo đúng cách ứng dụng sẽ được khởi động khi triển khai.

### 1.3. Vì sao phải dùng cả hai?

Phân tích tĩnh có thể xác nhận mô-đun ứng dụng chỉ đọc một API module cần thiết, nhưng không chứng minh mọi service provider đều có mặt. Kiểm thử runtime có thể xác nhận một provider chạy được, nhưng không tự chỉ ra rằng module descriptor đang khai báo một dependency dư thừa.

Cần đọc hai kết quả cùng nhau để phân biệt:

- Phụ thuộc được tham chiếu trực tiếp trong bytecode.
- Phụ thuộc được khai báo trong module descriptor.
- Provider được tìm thấy qua cơ chế service binding.
- Thành phần chỉ xuất hiện ở một nhánh runtime hoặc được nạp động.

## 2. Dùng jdeps để phân tích phụ thuộc tĩnh

**jdeps** phân tích phụ thuộc ở cấp package, class và module. Với dự án JPMS, đặt các mô-đun cần phân tích trên module path và chỉ định mô-đun gốc.

### 2.1. Kiểm tra module descriptor với --check

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Tùy chọn **--check** phân tích phụ thuộc của mô-đun được chỉ định. Kết quả có thể gồm module descriptor hiện tại, descriptor được đề xuất dựa trên phụ thuộc tìm thấy, đồ thị phụ thuộc sau khi rút gọn các cạnh readability đã được suy ra và qualified export không được sử dụng nếu có.

Đối chiếu descriptor hiện tại với descriptor được đề xuất. Nếu công cụ chỉ ra một **requires** không cần thiết, hãy kiểm tra lại ý định kiến trúc trước khi xóa. Một phụ thuộc có thể được giữ lại có chủ đích để cung cấp API cho consumer hoặc để thể hiện ranh giới mô-đun rõ ràng.

### 2.2. Liệt kê module dependencies

~~~bash
jdeps --module-path mods --list-deps --module com.example.app
~~~

Lệnh này liệt kê các module dependencies được công cụ suy ra từ phạm vi phân tích. Có thể dùng **--no-recursive** nếu chỉ muốn xem phụ thuộc không đệ quy theo yêu cầu cụ thể.

Kết quả giúp phát hiện mô-đun hoặc thư viện mà bytecode tham chiếu. Nó không phải danh sách đầy đủ mọi thành phần có thể được nạp trong tất cả tình huống runtime.

### 2.3. In danh sách module để đóng gói

~~~bash
jdeps --module-path mods --print-module-deps --module com.example.app
~~~

**--print-module-deps** in danh sách module dependency dạng phân tách bằng dấu phẩy. Kết quả có thể được dùng làm đầu vào khi xây dựng runtime image với **jlink**.

Nếu ứng dụng sử dụng ServiceLoader hoặc plugin, hãy kiểm tra riêng các mô-đun provider. Một provider được liên kết qua service binding không nhất thiết xuất hiện như một cạnh **requires** trực tiếp của mô-đun tiêu thụ.

### 2.4. Tìm phụ thuộc bị thiếu

~~~bash
jdeps --module-path mods --missing-deps --module com.example.app
~~~

**--missing-deps** tìm các phụ thuộc mà công cụ không giải quyết được trong phạm vi phân tích. Khi có kết quả, kiểm tra module path, class path và các artifact đã cung cấp cho jdeps.

Không nên coi kết quả không có cảnh báo là bằng chứng mọi lớp được nạp động đều tồn tại. Tên lớp được ghép từ chuỗi, reflection hoặc plugin được cài thêm lúc chạy có thể không xuất hiện như một tham chiếu bytecode thông thường.

### 2.5. Kiểm tra tham chiếu API nội bộ của JDK

~~~bash
jdeps --jdk-internals --module-path mods --module com.example.app
~~~

Tùy chọn **--jdk-internals** giúp tìm tham chiếu tới API nội bộ của JDK trong phạm vi phân tích. Những API này không phải hợp đồng tương thích công khai. Nếu có kết quả, nên tìm API được hỗ trợ thay thế và kiểm thử lại trên JDK mục tiêu.

Không dùng kết quả jdeps như một chứng nhận tương thích hoàn chỉnh. Nó là một nguồn bằng chứng tĩnh để hướng dẫn việc kiểm tra và sửa dependency.

## 3. Kiểm tra module graph khi JVM khởi chạy

### 3.1. --show-module-resolution

Có thể yêu cầu launcher hiển thị quá trình phân giải mô-đun:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Kết quả giúp quan sát các mô-đun gốc được đưa vào cấu hình chạy, các quan hệ **requires** được phân giải, các mô-đun provider được liên kết qua service binding và các mô-đun nền tảng được bind theo module graph.

Đầu ra này là thông tin chẩn đoán runtime. Nó không thay thế assertion hoặc integration test để xác nhận kết quả nghiệp vụ.

### 3.2. Service binding có thể làm runtime graph khác danh sách requires

Giả sử mô-đun ứng dụng khai báo:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Task;
}
~~~

Mô-đun provider khai báo:

~~~java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.Task
        with com.example.provider.UppercaseTask;
}
~~~

Ứng dụng chỉ có **requires com.example.spi**. Nó không cần khai báo **requires com.example.provider** để tham chiếu trực tiếp implementation. Khi mô-đun ứng dụng đã được phân giải và khai báo **uses**, cơ chế service binding có thể đưa mô-đun provider quan sát được trên module path vào cấu hình runtime.

Vì vậy, **jdeps --list-deps** trên riêng mô-đun ứng dụng có thể chỉ liệt kê **com.example.spi** và **java.base**, trong khi **java --show-module-resolution** cho thấy **com.example.provider** được bind cho service.

Đây là một trường hợp điển hình mà việc đối chiếu tĩnh và runtime giúp tránh kết luận sai về dependency graph.

## 4. Ví dụ hoàn chỉnh: jdeps và ServiceLoader

Ví dụ gồm ba mô-đun:

- **com.example.spi** định nghĩa service interface.
- **com.example.app** sử dụng service.
- **com.example.provider** cung cấp implementation.

Ứng dụng chỉ biết interface **Task**. Implementation được tìm qua ServiceLoader.

Cấu trúc thư mục:

~~~text
src/
├── com.example.spi/
│   ├── module-info.java
│   └── com/example/spi/Task.java
├── com.example.app/
│   ├── module-info.java
│   └── com/example/app/Main.java
└── com.example.provider/
    ├── module-info.java
    └── com/example/provider/UppercaseTask.java
~~~

### 4.1. Mô-đun service API

Tệp **src/com.example.spi/module-info.java**:

~~~java
module com.example.spi {
    exports com.example.spi;
}
~~~

Tệp **src/com.example.spi/com/example/spi/Task.java**:

~~~java
package com.example.spi;

public interface Task {
    String execute(String input);
}
~~~

### 4.2. Mô-đun ứng dụng

Tệp **src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Task;
}
~~~

Tệp **src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

import java.util.ServiceLoader;
import com.example.spi.Task;

public final class Main {
    public static void main(String[] args) {
        Task task = ServiceLoader.load(Task.class)
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("No Task provider"));

        String result = task.execute("static and runtime");

        if (!"STATIC AND RUNTIME".equals(result)) {
            throw new AssertionError("Unexpected result: " + result);
        }

        System.out.println("provider-created-and-verified");
        System.out.println("result=" + result);
    }
}
~~~

**uses** khai báo service mà mô-đun ứng dụng tìm qua ServiceLoader. Phần kiểm tra kết quả trong Main là một assertion runtime đơn giản: ứng dụng xác nhận provider đã thực hiện đúng hành vi mong đợi.

### 4.3. Mô-đun provider

Tệp **src/com.example.provider/module-info.java**:

~~~java
module com.example.provider {
    requires com.example.spi;

    provides com.example.spi.Task
        with com.example.provider.UppercaseTask;
}
~~~

Tệp **src/com.example.provider/com/example/provider/UppercaseTask.java**:

~~~java
package com.example.provider;

import com.example.spi.Task;

public final class UppercaseTask implements Task {
    public UppercaseTask() {
        System.out.println("provider-constructor");
    }

    @Override
    public String execute(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Constructor in một dòng log để kiểm tra provider thực sự được khởi tạo. **Locale.ROOT** giúp phép chuyển chữ hoa không phụ thuộc locale của máy chạy.

## 5. Biên dịch, phân tích tĩnh và chạy kiểm thử

Thực hiện từ thư mục chứa **src**.

### 5.1. Biên dịch cả ba mô-đun

~~~bash
javac -d mods --module-source-path src -m com.example.spi,com.example.app,com.example.provider
~~~

Lệnh này kiểm tra cú pháp, kiểu và các quan hệ mô-đun cần thiết cho quá trình biên dịch. Biên dịch thành công chưa xác nhận provider có được tìm thấy khi chạy.

### 5.2. Phân tích mô-đun ứng dụng bằng jdeps

~~~bash
jdeps --module-path mods --check com.example.app
~~~

Một phần kết quả trên JDK 24:

~~~text
[Module descriptor]
    requires com.example.spi;
    requires mandated java.base (@24.0.2);
[Suggested module descriptor for com.example.app]
    requires com.example.spi;
    requires mandated java.base;
[Transitive reduced graph for com.example.app]
    requires com.example.spi;
    requires mandated java.base;
~~~

Tiếp tục liệt kê dependencies:

~~~bash
jdeps --module-path mods --list-deps --module com.example.app
~~~

Kết quả:

~~~text
   com.example.spi
   java.base
~~~

Và danh sách rút gọn dạng một dòng:

~~~bash
jdeps --module-path mods --print-module-deps --module com.example.app
~~~

Kết quả:

~~~text
com.example.spi,java.base
~~~

**com.example.provider** không xuất hiện trong danh sách **requires** tĩnh của ứng dụng. Đó là kết quả phù hợp với thiết kế: ứng dụng phụ thuộc vào service API và tìm implementation qua service binding.

### 5.3. Chạy ứng dụng và xem module resolution

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Trong phần log module resolution, chú ý các dòng có ý nghĩa:

~~~text
root com.example.app ...
com.example.app requires com.example.spi ...
com.example.app binds com.example.provider ...
com.example.provider requires com.example.spi ...
~~~

Các đường dẫn artifact và những mô-đun nền tảng khác được runtime in ra tùy JDK và môi trường.

Kết quả stdout của chương trình:

~~~text
provider-constructor
provider-created-and-verified
result=STATIC AND RUNTIME
~~~

Kết quả cho thấy JVM đã tìm thấy provider, khởi tạo implementation và thực thi đúng hành vi. Runtime graph có mô-đun provider được bind, dù mô-đun ứng dụng không khai báo **requires com.example.provider**.

### 5.4. Kiểm tra tình huống thiếu provider

Để xác nhận kiểm thử có thể phát hiện lỗi triển khai, tạo một module path chỉ chứa **com.example.spi** và **com.example.app**, không có artifact **com.example.provider**, rồi chạy lại:

~~~bash
java --module-path mods-without-provider -m com.example.app/com.example.app.Main
~~~

Ứng dụng sẽ dừng tại lời gọi **orElseThrow()** với lỗi:

~~~text
Exception in thread "main" java.lang.IllegalStateException: No Task provider
~~~

Đây là lỗi runtime mà kết quả phân tích tĩnh trên hai mô-đun ứng dụng và SPI không thể loại trừ. Mô-đun ứng dụng có thể biên dịch và jdeps có thể phân tích thành công, nhưng cấu hình triển khai vẫn thiếu provider cần thiết.

## 6. Đối chiếu kết quả tĩnh và runtime

Từ ví dụ trên, có thể lập bảng đối chiếu:

| Nội dung cần xác minh | Phân tích tĩnh | Kiểm thử lúc chạy |
|---|---|---|
| App đọc service API | jdeps liệt kê **com.example.spi** | JVM phân giải **requires** |
| Provider có trong danh sách requires của app | Không; đây không phải requires trực tiếp | Service binding có thể bind provider |
| Provider artifact có sẵn | Phân tích riêng module path/artifact | ServiceLoader tìm được provider |
| Constructor provider hợp lệ | Không thực thi constructor | Constructor chạy thành công |
| Hành vi của implementation | Không xác nhận kết quả nghiệp vụ | Assertion xác nhận kết quả |
| Thiếu provider ở môi trường triển khai | Có thể không phát hiện từ dependency tĩnh của app | Test thất bại với **No Task provider** |
| Module descriptor có dependency thừa | jdeps có thể đề xuất descriptor gọn hơn | Test runtime không tự phát hiện dependency thừa |

Không nên yêu cầu hai công cụ phải in ra cùng một danh sách. Chúng quan sát những khía cạnh khác nhau của hệ thống.

Khi kết quả không khớp kỳ vọng:

1. Xác định module dependency xuất phát từ **requires**, tham chiếu bytecode hay service binding.
2. Kiểm tra module path và artifact thực tế.
3. Đọc **--show-module-resolution** để xác định mô-đun nào được phân giải và bind.
4. Chạy test trên đúng launcher command và đúng JDK.
5. Sửa descriptor hoặc cấu hình triển khai theo nguyên nhân đã xác minh, sau đó chạy lại cả phân tích tĩnh lẫn test.

## 7. Những giới hạn cần nhớ

### 7.1. Phân tích tĩnh không thực thi mã động

Các trường hợp sau có thể không xuất hiện như dependency thông thường trong bytecode:

- Tên lớp được tạo từ chuỗi và nạp bằng reflection.
- Provider hoặc plugin được cài thêm sau khi build.
- ModuleLayer được tạo động từ một thư mục plugin.
- Lớp được nạp qua class loader tùy chỉnh.
- Tên tài nguyên, cấu hình hoặc script được quyết định lúc chạy.

Với những trường hợp này, hãy bổ sung kiểm thử runtime và kiểm tra artifact/configuration thực tế.

### 7.2. Kiểm thử runtime chỉ bao phủ luồng đã chạy

Một bài test thành công chỉ xác nhận đường đi đã được thực thi trong môi trường test. Nó không chứng minh mọi provider, mọi cấu hình hoặc mọi nhánh điều kiện đều hoạt động.

Nên bổ sung test cho provider thay thế, thiếu provider, sai cấu hình, module path không đầy đủ và các nhánh nghiệp vụ quan trọng.

### 7.3. Không nhầm service binding với requires

**uses** và **provides** mô tả quan hệ dịch vụ. Chúng không giống một câu lệnh **requires** thông thường. Vì vậy, không nên tự thêm **requires** trực tiếp tới từng plugin chỉ để làm danh sách jdeps trông giống runtime graph, trừ khi ứng dụng thực sự cần phụ thuộc API của mô-đun đó.

Nếu tạo custom runtime image, hãy kiểm tra rằng các provider cần thiết được đưa vào image. Danh sách **--print-module-deps** của mô-đun consumer có thể không bao gồm mọi provider được bind ở runtime. Có thể chỉ định provider làm root của image hoặc cấu hình bước tạo image để liên kết service provider, sau đó chạy test trên image đã tạo.

### 7.4. Phân biệt lỗi phân giải với lỗi thực thi

Một số lỗi thường gặp:

- **FindException** hoặc **ResolutionException**: artifact/module descriptor hoặc dependency graph không phân giải được.
- **LayerInstantiationException**: việc định nghĩa layer thất bại.
- **ServiceConfigurationError**: cấu hình/provider service không hợp lệ hoặc quá trình tìm/khởi tạo provider thất bại.
- **ClassNotFoundException** hoặc **NoClassDefFoundError**: lớp cần thiết không được tìm thấy trong ngữ cảnh nạp lớp.
- **IllegalAccessError**: mã đã biên dịch nhưng quyền truy cập tại runtime không đáp ứng.
- **AssertionError** hoặc lỗi nghiệp vụ: mã đã chạy nhưng kết quả không đúng kỳ vọng.

Đọc loại lỗi và stack trace trước khi sửa module descriptor. Không phải mọi lỗi runtime đều là lỗi **requires**.

## 8. Quy trình áp dụng trong CI

Một pipeline kiểm tra mô-đun có thể sắp xếp theo thứ tự:

1. **Compile:** biên dịch các mô-đun bằng module source path hoặc build tool đã cấu hình.
2. **Static dependency analysis:** chạy **jdeps --check**, **--list-deps**, **--missing-deps** và **--jdk-internals** khi phù hợp.
3. **Review descriptor:** đối chiếu dependency được phát hiện với **requires**, **exports**, **uses** và **provides**.
4. **Runtime resolution:** chạy ứng dụng với **--show-module-resolution** ở bước chẩn đoán khi cần.
5. **Integration test:** chạy trên module path thực tế, kiểm tra provider, reflection, tài nguyên và hành vi nghiệp vụ.
6. **Packaging test:** nếu phát hành runtime image hoặc plugin bundle, chạy test trên đúng artifact đã đóng gói.
7. **Regression test:** chạy lại sau khi nâng JDK, cập nhật thư viện hoặc thay đổi module descriptor.

Để kết quả có thể tái lập, lưu lại JDK version, lệnh **javac**/**jdeps**/**java**, module path, danh sách artifact và kết quả test. Không chỉ chạy test qua IDE nếu sản phẩm được triển khai bằng module path riêng.

## 9. Checklist nghiệm thu

- [ ] Các mô-đun biên dịch thành công trên JDK mục tiêu.
- [ ] **jdeps --check** đã được xem xét và không còn dependency bất ngờ.
- [ ] **jdeps --list-deps** và **--print-module-deps** phù hợp với mục tiêu phân tích.
- [ ] **--missing-deps** không báo thiếu dependency trong phạm vi artifact được kiểm tra.
- [ ] Không có tham chiếu JDK internal API chưa được xử lý.
- [ ] **uses** và **provides** khai báo đúng service type.
- [ ] Provider cần thiết có mặt trên module path hoặc trong layer tương ứng.
- [ ] Runtime module resolution cho thấy các mô-đun cần thiết đã được phân giải/bind.
- [ ] Integration test gọi được provider và xác nhận kết quả nghiệp vụ.
- [ ] Đã thử tình huống thiếu provider hoặc cấu hình runtime không đầy đủ.
- [ ] Runtime image/plugin bundle đã được kiểm tra sau đóng gói.
- [ ] Kết quả được kiểm tra lại sau thay đổi JDK, thư viện hoặc module descriptor.

**Nguyên tắc áp dụng:** dùng **jdeps** để hiểu phụ thuộc tĩnh và chất lượng module descriptor; dùng **--show-module-resolution** để quan sát module graph khi JVM khởi chạy; dùng integration test để xác nhận provider và hành vi thực tế. Khi ba nguồn bằng chứng được đối chiếu trên cùng artifact và cấu hình triển khai, nhóm phát triển có thể phân biệt rõ dependency tĩnh, service binding và lỗi chỉ xuất hiện lúc chạy.