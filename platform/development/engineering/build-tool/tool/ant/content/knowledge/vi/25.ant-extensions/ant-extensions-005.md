# Vòng đời task, phương thức init và execute

Khi viết custom task cho Apache Ant, hai phương thức quan trọng nhất là `init()` và `execute()`. Chúng được gọi ở hai thời điểm khác nhau trong vòng đời của một task: `init()` chuẩn bị task khi Ant bắt đầu thực thi nó, còn `execute()` chạy công việc chính sau khi Ant đã cấu hình các thuộc tính và phần tử XML lồng bên trong.

Hiểu đúng thứ tự này giúp tránh các lỗi như đọc thuộc tính XML quá sớm, gọi `getProject()` trong constructor, hoặc giữ trạng thái trong một task instance với giả định nó tồn tại suốt toàn bộ build.

## 1. Task không được tạo ngay khi Ant đọc build file

Khi Ant đọc `build.xml`, nó phân tích cấu trúc XML và ghi nhận phần tử task trong target. Ở giai đoạn này, Ant thường biểu diễn phần tử task bằng một đối tượng trung gian `UnknownElement`. Task Java thực tế chưa nhất thiết được khởi tạo.

Khi target được thực thi, Ant mới tạo instance của task, gắn thông tin project và target, cấu hình dữ liệu XML rồi gọi phần thực thi.

```text
Đọc và phân tích build.xml
          |
          v
Tạo cấu trúc UnknownElement
          |
          v
Target bắt đầu chạy
          |
          v
Khởi tạo task instance
          |
          v
Gắn Project, Location, Target
          |
          v
Gọi init()
          |
          v
Cấu hình attributes và nested elements
          |
          v
Gọi execute() qua Task.perform()
          |
          v
Task hoàn tất hoặc ném BuildException
```

Vì task được tạo ở thời điểm chạy target, constructor của custom task không phải nơi thích hợp để truy cập project hoặc đọc giá trị cấu hình từ XML.

## 2. Thứ tự vòng đời task trong Ant

Theo vòng đời task của Ant, các bước chính diễn ra như sau:

1. Ant phân tích XML và tạo `UnknownElement` tương ứng với task trong build file.
2. Khi target chạy, Ant thực hiện `UnknownElement`; task instance được khởi tạo lúc runtime.
3. Ant gắn `Project` và vị trí phần tử trong build file (`Location`) vào task.
4. Nếu phần tử task có thuộc tính `id`, Ant đăng ký reference tương ứng trong project.
5. Ant gắn target sở hữu task vào task instance.
6. Ant gọi `init()`.
7. Các nested element được tạo qua `createXXX()` hoặc được khởi tạo rồi chuyển cho `addXXX()`; với `addConfiguredXXX()`, object con được tạo nhưng callback addConfigured chưa được gọi ở bước này.
8. Các thuộc tính của task cha được gán qua các phương thức `setXXX()`.
9. Nội dung text trực tiếp bên trong phần tử task được chuyển qua `addText(String)` nếu task có phương thức này.
10. Các thuộc tính và nested element bên trong từng object con được cấu hình.
11. Các callback `addConfiguredXXX()` được gọi sau khi object con đã được cấu hình.
12. Ant gọi phần thực thi của task: `Task.perform()` gọi `execute()` và xử lý các build event tương ứng.

Có hai điều cần nhớ về thứ tự trên:

- `init()` chạy trước khi các thuộc tính XML của task được gán. Không đọc `message`, `file`, `mode` hoặc thuộc tính do người dùng khai báo trong `init()`.
- Không dựa vào thứ tự gọi giữa các setter như `setFile()` và `setMode()`. Hãy kiểm tra các giá trị liên quan cùng nhau trong `execute()` sau khi cấu hình hoàn tất.

## 3. Constructor: chỉ khởi tạo trạng thái Java cơ bản

Ant tạo task bằng constructor không tham số theo cách thông thường. Tại thời điểm constructor chạy, task chưa được gắn với project.

Ví dụ không nên làm:

```java
public class GreetingTask extends Task {

    public GreetingTask() {
        // Không nên: getProject() chưa được Ant gắn vào task.
        log(getProject().getName());
    }
}
```

`getProject()` có thể trả về `null` trong constructor. Constructor chỉ nên thiết lập giá trị mặc định cho field Java hoặc tạo collection nội bộ:

```java
public class GreetingTask extends Task {

    private String message;
    private String level = "INFO";
}
```

Ant sẽ gắn project và cấu hình các thuộc tính XML sau khi instance được tạo. Nếu cần dùng project, location, logger hoặc property của build, hãy truy cập sau khi task đã được gắn vào project, thường trong setter hoặc `execute()`.

## 4. init(): hook khởi tạo task trước khi cấu hình XML

`init()` là phương thức vòng đời được Ant gọi sau khi task instance được gắn project/location/target nhưng trước khi các thuộc tính XML và nested element được cấu hình.

Có thể override để chuẩn bị trạng thái không phụ thuộc vào các thuộc tính XML:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

public class GreetingTask extends Task {

    private String message;

    @Override
    public void init() throws BuildException {
        super.init();
        log("GreetingTask initialized", Project.MSG_VERBOSE);
    }

    public void setMessage(String message) {
        this.message = message;
    }

    @Override
    public void execute() throws BuildException {
        if (message == null || message.trim().isEmpty()) {
            throw new BuildException("Attribute 'message' is required.", getLocation());
        }

        log(message, Project.MSG_INFO);
    }
}
```

Trong ví dụ, `init()` chỉ ghi log ở mức verbose. Nó không đọc `message`, vì `setMessage()` chỉ được Ant gọi sau đó. `execute()` chạy khi giá trị `message` đã được gán.

Nên gọi `super.init()` khi override để giữ hành vi khởi tạo của lớp cha. Không dùng `init()` để thực hiện công việc nghiệp vụ chính hoặc đọc thuộc tính của task.

## 5. execute(): nơi thực hiện công việc chính

`execute()` là phương thức mà custom task phải triển khai. Ant gọi nó sau khi đã cấu hình task và nested elements.

Một chữ ký thông dụng:

```java
@Override
public void execute() throws BuildException {
    // Validate cấu hình và thực hiện công việc của task.
}
```

Trong `execute()`, task có thể:

- Đọc các field đã được setter gán.
- Đọc nested element đã được tạo và cấu hình.
- Truy cập project qua `getProject()`.
- Ghi log qua `log()`.
- Kiểm tra file, property hoặc reference.
- Thực hiện công việc chính.
- Ném `BuildException` nếu cấu hình hoặc thao tác không hợp lệ.

Ví dụ kiểm tra đầu vào và báo lỗi có vị trí trong build file:

```java
@Override
public void execute() throws BuildException {
    if (message == null || message.trim().isEmpty()) {
        throw new BuildException(
            "The message attribute must not be empty.",
            getLocation()
        );
    }

    log("Project: " + getProject().getName(), Project.MSG_VERBOSE);
    log(message, Project.MSG_INFO);
}
```

`getLocation()` giúp Ant gắn lỗi với vị trí phần tử task trong XML. Điều này hữu ích khi cùng một custom task được gọi nhiều lần trong nhiều target.

## 6. Ví dụ hoàn chỉnh: custom task có init và execute

Giả sử custom task được đóng gói trong `build/ant-tasks.jar`. Lớp Java:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

public class GreetingTask extends Task {

    private String message;
    private String prefix = "INFO";

    @Override
    public void init() throws BuildException {
        super.init();
        log("init() called", Project.MSG_VERBOSE);
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public void execute() throws BuildException {
        if (message == null || message.trim().isEmpty()) {
            throw new BuildException(
                "The 'message' attribute is required.",
                getLocation()
            );
        }

        log("[" + prefix + "] " + message, Project.MSG_INFO);
    }
}
```

Khai báo task và sử dụng trong `build.xml`:

```xml
<project name="custom-task-demo" default="run" basedir=".">

    <target name="register-task">
        <taskdef name="greet"
                 classname="com.example.ant.GreetingTask">
            <classpath>
                <pathelement location="build/ant-tasks.jar"/>
            </classpath>
        </taskdef>
    </target>

    <target name="run" depends="register-task">
        <greet prefix="DEMO" message="Hello from a custom Ant task"/>
    </target>

</project>
```

Khi chạy:

```bash
ant -verbose run
```

Ant thực hiện target `register-task`, đăng ký tên task `greet`, rồi chạy target `run`. Khi đến phần tử `<greet>`, Ant tạo instance `GreetingTask`, gọi `init()`, gán `prefix` và `message`, rồi gọi `execute()`.

Ở mức log verbose, có thể quan sát thông báo `init() called`. Message chính được in ở mức info:

```text
[greet] [DEMO] Hello from a custom Ant task
```

Nếu bỏ thuộc tính `message`, task vẫn được tạo và khởi tạo; đến `execute()` nó phát hiện cấu hình thiếu và ném `BuildException` có vị trí trong build file.

## 7. Vì sao init không nên đọc thuộc tính task?

Xem build file:

```xml
<greet prefix="DEMO" message="Hello"/>
```

Một người mới có thể nghĩ Ant đọc `message` trước rồi mới gọi `init()`. Thực tế, vòng đời task gọi `init()` trước khi các setter của task cha được thực hiện.

Nếu viết:

```java
@Override
public void init() throws BuildException {
    super.init();
    log("Message: " + message);
}
```

thì `message` vẫn là `null` tại thời điểm đó. Giá trị XML chỉ được gán sau này qua `setMessage()`.

Hãy chuyển logic phụ thuộc vào cấu hình sang `execute()`:

```java
@Override
public void execute() throws BuildException {
    log("Message: " + message);
}
```

Nếu cần chuẩn hóa một giá trị ngay khi Ant gán thuộc tính, setter có thể xử lý giá trị đó. Tuy nhiên, nếu logic cần kết hợp nhiều thuộc tính, kiểm tra quan hệ giữa chúng hoặc phụ thuộc nested elements, nên thực hiện sau khi cấu hình hoàn tất trong `execute()`.

## 8. Thứ tự setter không phải hợp đồng để dựa vào

Ant dùng introspection để tìm setter phù hợp với các thuộc tính XML. Không nên giả định thứ tự các thuộc tính trong XML quyết định thứ tự setter hoặc Ant luôn gọi setter theo một trình tự cụ thể.

Ví dụ:

```xml
<archive source="build/classes" destination="dist/app.jar"/>
```

Ant có thể gọi `setSource()` và `setDestination()` theo thứ tự cấu hình nội bộ. Task không nên yêu cầu `setSource()` phải chạy trước `setDestination()`.

Thiết kế an toàn:

```java
private File source;
private File destination;

public void setSource(File source) {
    this.source = source;
}

public void setDestination(File destination) {
    this.destination = destination;
}

@Override
public void execute() throws BuildException {
    if (source == null) {
        throw new BuildException("Attribute 'source' is required.", getLocation());
    }
    if (destination == null) {
        throw new BuildException("Attribute 'destination' is required.", getLocation());
    }

    // Chỉ sử dụng source và destination sau khi cả hai đã được gán.
}
```

Setter chỉ lưu cấu hình. `execute()` kiểm tra tính đầy đủ và nhất quán của toàn bộ cấu hình trước khi thực hiện công việc.

## 9. Nested elements và create/add/addConfigured

Custom task có thể nhận phần tử XML lồng nhau. Ant hỗ trợ ba kiểu callback phổ biến:

| Cách khai báo | Khi nào Ant gọi | Đặc điểm |
|---|---|---|
| `createX()` | Khi cần tạo nested element | Task tự tạo object và trả object cho Ant cấu hình |
| `addX(X child)` | Khi object con được tạo | Task nhận object ngay sau khi constructor chạy, trước khi các thuộc tính con được cấu hình |
| `addConfiguredX(X child)` | Sau khi object con và thuộc tính/nested elements của nó đã được cấu hình | Task nhận object đã hoàn chỉnh để validate hoặc lưu lại |

Ví dụ task nhận nhiều phần tử `<rule>`:

```java
package com.example.ant;

import java.util.ArrayList;
import java.util.List;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class RuleTask extends Task {

    private final List<Rule> rules = new ArrayList<>();

    public void addConfiguredRule(Rule rule) {
        if (rule.getName() == null || rule.getName().trim().isEmpty()) {
            throw new BuildException("Each rule requires a name.", getLocation());
        }
        rules.add(rule);
    }

    @Override
    public void execute() throws BuildException {
        for (Rule rule : rules) {
            log(rule.getName() + " = " + rule.getValue());
        }
    }

    public static class Rule {
        private String name;
        private String value;

        public void setName(String name) {
            this.name = name;
        }

        public void setValue(String value) {
            this.value = value;
        }

        public String getName() {
            return name;
        }

        public String getValue() {
            return value;
        }
    }
}
```

Build file:

```xml
<rules>
    <rule name="environment" value="production"/>
    <rule name="region" value="ap-southeast-1"/>
</rules>
```

Ant tạo từng `Rule`, gán `name` và `value`, rồi gọi `addConfiguredRule()` sau khi object con đã được cấu hình. Vì vậy, callback có thể kiểm tra `name` và `value` một cách an toàn.

Nếu dùng `addRule()` thay vì `addConfiguredRule()`, callback nhận object trước khi các thuộc tính của nested element được gán. Khi cần validate object con ngay lúc nhận, `addConfigured` thường phù hợp hơn.

## 10. addText và nội dung text trực tiếp

Nếu task cho phép nội dung text trực tiếp bên trong phần tử XML, có thể triển khai `addText(String)`:

```java
public class NoticeTask extends Task {

    private String text;

    public void addText(String text) {
        this.text = text;
    }

    @Override
    public void execute() throws BuildException {
        if (text == null || text.trim().isEmpty()) {
            throw new BuildException("Text content is required.", getLocation());
        }
        log(text.trim());
    }
}
```

Sử dụng:

```xml
<notice>
    This is a notice from the build file.
</notice>
```

Ant chuyển phần text vào `addText()` trong giai đoạn cấu hình. Lưu ý: Ant không tự mở rộng property trong text mà nó chuyển cho `addText()`. Nếu cần thay thế property trong nội dung, task phải xử lý chủ động, ví dụ dùng `getProject().replaceProperties(text)` khi phù hợp.

## 11. Task instance có vòng đời theo từng lần thực thi

Không nên xem custom task như một singleton tồn tại suốt build. Ant khởi tạo task khi phần tử tương ứng được thực thi. Nếu cùng một target chạy nhiều lần trong một invocation, task instance của lần chạy sau không phải trạng thái tiếp nối đáng tin cậy của lần trước.

Ví dụ hai target cùng phụ thuộc vào target `prepare`:

```xml
<target name="prepare">
    <greet message="Preparing"/>
</target>

<target name="build-app" depends="prepare">
    <echo message="Build app"/>
</target>

<target name="build-docs" depends="prepare">
    <echo message="Build docs"/>
</target>
```

Khi chạy:

```bash
ant build-app build-docs
```

Ant có thể thực hiện target `prepare` hai lần vì mỗi target được yêu cầu đều có dependency đó. Các task bên trong `prepare` được tạo và thực thi theo từng lần target chạy.

Vì vậy:

- Không dựa vào field instance để giữ trạng thái qua nhiều lần gọi target.
- Không lưu dữ liệu build dùng chung trong static mutable field.
- Nếu cần chia sẻ trạng thái, dùng property hoặc reference của `Project` với quy ước rõ ràng.
- Nếu cần tránh chạy dependency lặp, tổ chức lại target graph thay vì dựa vào việc task tự nhớ đã chạy.

## 12. perform() và execute() khác nhau thế nào?

Trong custom task, phương thức cần override là `execute()`. Ant thực tế gọi `Task.perform()` để thực hiện task; `perform()` là lớp bao quanh quá trình cấu hình/thực thi và phát các build event như task started/task finished.

Không override `perform()` cho logic nghiệp vụ thông thường. Nếu tự gọi một task khác được tạo hoặc chứa bên trong task của mình, cần gọi `perform()` trên task đó để Ant xử lý build event đúng cách, thay vì gọi trực tiếp `execute()`.

Điểm cần nhớ:

```text
Ant gọi Task.perform()
        |
        +--> bảo đảm task được cấu hình
        |
        +--> phát build event
        |
        +--> gọi execute()
        |
        +--> phát event kết thúc, kể cả khi có lỗi
```

Vì vậy, `execute()` là nơi viết hành vi task; `perform()` thuộc cơ chế điều phối vòng đời của Ant.

## 13. Ghi log và báo lỗi đúng cách

Custom task nên dùng `log()` thay vì ghi trực tiếp vào `System.out` hoặc `System.err`. Log của Ant có các mức khác nhau:

| Mức | Hằng số | Mục đích |
|---|---|---|
| Error | `Project.MSG_ERR` | Lỗi cần chú ý |
| Warning | `Project.MSG_WARN` | Cảnh báo |
| Info | `Project.MSG_INFO` | Thông tin thông thường |
| Verbose | `Project.MSG_VERBOSE` | Chi tiết khi bật `-verbose` |
| Debug | `Project.MSG_DEBUG` | Chẩn đoán sâu khi bật `-debug` |

Ví dụ:

```java
log("Starting archive generation", Project.MSG_INFO);
log("Using source directory: " + source, Project.MSG_VERBOSE);
```

Khi đầu vào không hợp lệ hoặc thao tác không thể hoàn thành, ném `BuildException`:

```java
throw new BuildException("Source directory does not exist: " + source,
                         getLocation());
```

Nếu bắt một exception từ Java API, có thể bọc nguyên nhân và vị trí build file:

```java
try {
    // Perform the operation.
} catch (IOException ex) {
    throw new BuildException("Could not process the input file.", ex, getLocation());
}
```

Không bắt exception rồi chỉ in stack trace mà vẫn để task kết thúc như thành công. Ant cần nhận `BuildException` để đánh dấu build thất bại và dừng các bước phụ thuộc.

## 14. Những lỗi thường gặp trong vòng đời task

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `getProject()` trả về `null` | Gọi trong constructor | Truy cập sau khi Ant gắn project, thường trong `execute()` |
| Thuộc tính XML vẫn `null` trong init | `init()` chạy trước setter | Chỉ dùng `init()` cho khởi tạo không phụ thuộc XML |
| Setter này phụ thuộc setter khác | Giả định thứ tự setter cố định | Chỉ lưu giá trị trong setter, kiểm tra kết hợp trong `execute()` |
| Nested element thiếu thuộc tính khi được nhận | Dùng `addX()` nhưng mong object đã cấu hình | Dùng `addConfiguredX()` nếu cần object đã hoàn tất |
| Task chạy lại nhưng field giữ trạng thái không như dự kiến | Giả định task instance sống lâu hoặc được tái sử dụng | Thiết kế state theo từng lần thực thi; dùng project property/reference nếu thật sự cần chia sẻ |
| Build listener không nhận event task như mong đợi | Tự gọi `execute()` hoặc override `perform()` sai cách | Để Ant gọi `perform()` và override `execute()` |
| Lỗi Java bị nuốt, build vẫn chạy | Chỉ log exception, không ném lỗi Ant | Bọc lỗi bằng `BuildException` |
| Log xuất hiện dù không muốn ở chế độ quiet | Ghi trực tiếp `System.out` | Dùng `log()` với mức phù hợp |

## 15. Bài tập thực hành

1. Tạo class `GreetingTask extends Task` có thuộc tính `message`.
2. Override `init()` để ghi một thông báo ở mức verbose; không đọc `message` trong phương thức này.
3. Viết `setMessage()` và `execute()` để kiểm tra message rồi ghi log.
4. Đóng gói class vào JAR và đăng ký bằng `<taskdef>`.
5. Chạy task bằng XML có và không có thuộc tính `message`; quan sát thời điểm `BuildException` được ném.
6. Thêm thuộc tính `prefix`, đặt giá trị mặc định trong field và xác nhận setter có thể thay đổi giá trị trước `execute()`.
7. Tạo nested element `rule` và triển khai `addConfiguredRule()`; kiểm tra object con đã có đủ thuộc tính khi callback chạy.
8. Thêm `addText()` cho một custom task khác và quan sát nội dung XML được chuyển vào.
9. Chạy hai target cùng phụ thuộc vào một target có custom task; quan sát target và task có thể được thực hiện nhiều lần.
10. Thử ném `BuildException` có `getLocation()` và kiểm tra log Ant chỉ ra build file cùng vị trí lỗi.

## 16. Nguyên tắc thiết kế custom task

Hãy giữ constructor đơn giản và không truy cập project trong đó. Dùng `init()` cho phần khởi tạo cần thiết trước cấu hình XML, không đọc các thuộc tính task ở giai đoạn này. Setter chỉ nên nhận và lưu cấu hình; nested element nên được nhận bằng callback phù hợp với thời điểm cần xử lý object con. Đặt kiểm tra đầy đủ và logic nghiệp vụ trong `execute()`.

Khi task thất bại, ném `BuildException` có thông báo rõ và vị trí build file. Dùng `log()` để tích hợp với mức log của Ant. Đừng giả định task instance là singleton hoặc dependency target chỉ chạy một lần. Khi tuân theo thứ tự vòng đời này, custom task sẽ dễ hiểu, dễ debug và tương thích tốt hơn với cơ chế thực thi của Ant.

## 17. Tài liệu tham khảo

- [Apache Ant Manual: Writing Your Own Task](https://ant.apache.org/manual/develop.html)
- [Apache Ant Manual: Tutorial – Writing Tasks](https://ant.apache.org/manual/tutorial-writing-tasks.html)
- [Apache Ant API: Task](https://ant.apache.org/manual/api/org/apache/tools/ant/Task.html)
