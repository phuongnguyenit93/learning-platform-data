# Truy cập `Project`, property, reference và vị trí lỗi trong custom task

Khi viết custom task cho Apache Ant, lớp Java của task không hoạt động độc lập. Ant tạo đối tượng task, gắn nó với build project hiện tại, truyền các thuộc tính được khai báo trong XML rồi gọi phương thức thực thi. Nhờ ngữ cảnh này, custom task có thể đọc cấu hình chung, lấy các datatype đã khai báo trong build file và báo lỗi đúng vị trí nơi task được gọi.

Các API quan trọng nằm quanh ba khái niệm:

- **`Project`:** đại diện cho build project đang chạy, cung cấp property, reference, logging và thông tin cấu hình.
- **Property và reference:** property lưu giá trị cấu hình dạng chuỗi; reference trỏ đến đối tượng Ant như `Path`, `FileSet` hoặc datatype khác.
- **`Location`:** lưu vị trí trong build file để thông báo lỗi chỉ ra dòng XML có vấn đề.

Custom task thường kế thừa `org.apache.tools.ant.Task`. Lớp `Task` kế thừa `ProjectComponent`, vì vậy task có thể gọi `getProject()`, `getLocation()` và `log(...)` mà không cần tự tạo một project mới.

Sau bài học, bạn có thể:

- Hiểu cách Ant gắn `Project` và `Location` vào custom task.
- Đọc property bằng `Project.getProperty()` và xử lý giá trị chưa được khai báo.
- Tạo property mới bằng `Project.setNewProperty()`.
- Đọc reference bằng `Project.getReference()` và kiểm tra kiểu đối tượng.
- Làm việc với `Path` và các reference được khai báo trong build file.
- Ghi log theo cấp độ phù hợp.
- Ném `BuildException` có kèm vị trí task để thông báo lỗi hữu ích.
- Tổ chức custom task có thể tái sử dụng và dễ kiểm thử.

## 1. Ngữ cảnh thực thi của custom task

Một custom task là một lớp Java mà Ant có thể khởi tạo từ build file. Ví dụ, build file gọi:

```xml
<project name="custom-task-demo" default="run">
    <taskdef name="helloTask"
             classname="com.example.ant.HelloTask"
             classpath="build/custom-tasks.jar" />

    <target name="run">
        <helloTask />
    </target>
</project>
```

Khi Ant xử lý phần tử `<helloTask>`, nó thực hiện các bước khái quát:

1. Tìm định nghĩa task đã đăng ký bằng `taskdef`.
2. Tạo một đối tượng `HelloTask`.
3. Gắn project hiện tại và thông tin vị trí XML vào đối tượng task.
4. Đọc các thuộc tính XML và gọi các setter tương ứng trên task.
5. Cấu hình các phần tử lồng nhau nếu task có khai báo.
6. Gọi `execute()` khi target được thực thi.

Vì Ant đã gắn ngữ cảnh trước khi gọi `execute()`, task có thể lấy project hiện tại bằng `getProject()` và vị trí trong build file bằng `getLocation()`.

### 1.1. Kế thừa `Task`

Lớp custom task cơ bản thường có dạng:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class HelloTask extends Task {
    @Override
    public void execute() throws BuildException {
        log("Hello from a custom Ant task");
    }
}
```

`Task` cung cấp các chức năng cơ bản:

- Liên kết với `Project` đang chạy.
- Lấy `Location` của phần tử task trong build file.
- Ghi log theo cấp độ Ant.
- Truy cập thông tin như tên task và target sở hữu task.
- Cung cấp vòng đời thực thi mà Ant gọi.

Không cần tự tạo `new Project()` trong custom task thông thường. Làm như vậy sẽ tạo một project tách rời, không chứa property, reference và cấu hình mà người dùng đã khai báo trong build file hiện tại.

### 1.2. `ProjectComponent` và `Task`

`Task` kế thừa `ProjectComponent`. Các phương thức ngữ cảnh phổ biến được định nghĩa ở lớp cơ sở này hoặc được task kế thừa:

| API | Công dụng |
|---|---|
| `getProject()` | Lấy `Project` mà Ant đã gắn cho task. |
| `getLocation()` | Lấy vị trí task trong build file. |
| `log(String)` | Ghi thông báo ở mức thông tin mặc định. |
| `log(String, int)` | Ghi thông báo với cấp độ log chỉ định. |
| `getTaskName()` | Lấy tên task được khai báo hoặc đăng ký trong Ant. |
| `getOwningTarget()` | Lấy target chứa task. |

Các API này giúp custom task hoạt động theo ngữ cảnh build hiện tại thay vì phải nhận mọi thông tin qua thuộc tính XML.

## 2. Truy cập `Project` bằng `getProject()`

`getProject()` trả về đối tượng `org.apache.tools.ant.Project` gắn với task. `Project` là trung tâm quản lý trạng thái của một lần build, bao gồm property, reference, target, listener, base directory và một số dịch vụ khác.

Ví dụ đọc tên project và thư mục cơ sở:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

public class ProjectInfoTask extends Task {
    @Override
    public void execute() throws BuildException {
        Project project = getProject();

        if (project == null) {
            throw new BuildException(
                "The task is not attached to an Ant Project",
                getLocation()
            );
        }

        log("Project name: " + project.getName());
        log("Base directory: " + project.getBaseDir());
    }
}
```

Khi task được Ant gọi trong build file, `getProject()` thông thường đã có giá trị. Kiểm tra `null` vẫn hữu ích nếu lớp được tạo trực tiếp trong một chương trình Java hoặc trong unit test mà chưa được gắn vào project.

### 2.1. Những thông tin thường lấy từ `Project`

Một số phương thức hữu ích:

| Phương thức | Ý nghĩa |
|---|---|
| `getName()` | Tên project được khai báo trong phần tử `<project>`. |
| `getBaseDir()` | Thư mục cơ sở của project. |
| `getProperty(name)` | Đọc giá trị property theo tên. |
| `getUserProperty(name)` | Đọc user property, thường được truyền từ dòng lệnh hoặc cấu hình cấp cao. |
| `getReference(id)` | Lấy đối tượng được đăng ký bằng reference ID. |
| `addReference(id, value)` | Đăng ký một đối tượng dưới một reference ID. |
| `replaceProperties(text)` | Thay các biểu thức property `${...}` có thể phân giải trong chuỗi. |
| `resolveFile(path)` | Phân giải đường dẫn theo thư mục cơ sở của project. |

Không nên lấy toàn bộ trạng thái project nếu task chỉ cần một giá trị. Truy cập theo tên property hoặc reference ID giúp task có hợp đồng rõ ràng và dễ kiểm thử.

### 2.2. Không tự tạo project khác để đọc cấu hình

Đoạn code sau thường là sai ý định:

```java
Project project = new Project();
String version = project.getProperty("release.version");
```

Project mới không tự nhận các property đã khai báo trong build file đang chạy, vì vậy `version` có thể là `null`.

Trong custom task, hãy dùng:

```java
Project project = getProject();
String version = project.getProperty("release.version");
```

Đây là project mà Ant đã cấu hình cho task.

## 3. Đọc property trong custom task

Property của Ant thường được dùng để lưu cấu hình dạng chuỗi như version, đường dẫn, tên môi trường hoặc cờ bật/tắt một chức năng.

Build file:

```xml
<project name="property-demo" default="run">
    <property name="release.version" value="2.3.0" />
    <property name="deploy.environment" value="staging" />

    <target name="run">
        <projectInfo propertyName="release.version" />
    </target>
</project>
```

Custom task có thể nhận tên property qua setter rồi đọc giá trị trong `execute()`:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

public class ProjectInfoTask extends Task {
    private String propertyName;

    public void setPropertyName(String propertyName) {
        this.propertyName = propertyName;
    }

    @Override
    public void execute() throws BuildException {
        if (propertyName == null || propertyName.trim().isEmpty()) {
            throw new BuildException(
                "Attribute 'propertyName' is required",
                getLocation()
            );
        }

        Project project = getProject();
        String value = project.getProperty(propertyName);

        if (value == null) {
            log("Property '" + propertyName + "' is not defined",
                Project.MSG_WARN);
            return;
        }

        log(propertyName + " = " + value);
    }
}
```

Ant ánh xạ thuộc tính XML `propertyName` tới phương thức `setPropertyName(...)`. Setter chỉ lưu tên property; việc đọc giá trị được thực hiện khi task chạy.

### 3.1. `getProperty()` trả về gì?

```java
String value = getProject().getProperty("release.version");
```

- Nếu property tồn tại, phương thức trả về giá trị dạng `String`.
- Nếu property chưa được khai báo, phương thức trả về `null`.
- Giá trị property không tự chuyển thành kiểu Java khác. Nếu cần số hoặc boolean, task phải kiểm tra và phân tích chuỗi.

Ví dụ đọc số:

```java
String raw = getProject().getProperty("retry.count");

if (raw == null) {
    throw new BuildException("Property retry.count is required", getLocation());
}

final int retryCount;
try {
    retryCount = Integer.parseInt(raw.trim());
} catch (NumberFormatException ex) {
    throw new BuildException(
        "Property retry.count must be an integer: " + raw,
        ex,
        getLocation()
    );
}
```

Không nên dùng `Integer.parseInt()` trực tiếp trên giá trị có thể `null` hoặc không hợp lệ mà không xử lý lỗi. Custom task nên báo rõ tên property và giá trị không chấp nhận được.

### 3.2. Phân biệt property thường và user property

Ant có nhiều nguồn property. Ví dụ:

```bash
ant -Drelease.version=2.4.0 package
```

Giá trị truyền bằng `-D` là user property. Trong custom task:

```java
Project project = getProject();

String version = project.getProperty("release.version");
String userVersion = project.getUserProperty("release.version");
```

`getProperty()` đọc giá trị property hiệu lực. `getUserProperty()` chỉ trả về giá trị nếu tên đó được đặt dưới dạng user property. Nếu property được khai báo trong build file mà không phải user property, `getUserProperty()` có thể trả về `null` trong khi `getProperty()` vẫn có giá trị.

Trong đa số custom task, `getProperty()` là API phù hợp để lấy giá trị cấu hình đang có hiệu lực. Chỉ dùng `getUserProperty()` khi task cần phân biệt rõ giá trị được người gọi truyền từ bên ngoài với giá trị mặc định trong build file.

### 3.3. Property của Ant có tính bất biến

Task `<property>` và API `Project.setNewProperty()` tuân theo quy tắc property thông thường của Ant: một property đã được đặt sẽ không bị ghi đè bởi lần đặt sau.

Ví dụ:

```xml
<property name="release.version" value="1.0.0" />
<property name="release.version" value="2.0.0" />
```

Giá trị đầu tiên vẫn có hiệu lực. Đây là đặc điểm giúp build nhận cấu hình từ dòng lệnh rồi giữ nguyên cấu hình đó trong suốt lần chạy.

Vì vậy, custom task không nên dùng property như một biến có thể thay đổi liên tục. Nếu cần lưu trạng thái có thể cập nhật trong lúc build, hãy dùng reference hoặc trạng thái nội bộ của task. Nếu cần xuất một kết quả build thành property mới, dùng `setNewProperty()` và chọn tên chưa được sử dụng.

## 4. Tạo property mới bằng `setNewProperty()`

Custom task có thể công bố kết quả cho các task tiếp theo bằng cách đặt property mới trên project:

```java
Project project = getProject();
project.setNewProperty("build.summary", "module=core;status=ready");
```

Sau đó build file có thể dùng:

```xml
<inspectBuild />
<echo message="${build.summary}" />
```

`setNewProperty(name, value)` chỉ đặt property nếu tên đó chưa có giá trị. Nếu property đã được đặt từ dòng lệnh hoặc một task trước đó, giá trị cũ vẫn được giữ.

### 4.1. Ví dụ task đọc rồi xuất property

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

public class BuildLabelTask extends Task {
    private String sourceProperty;
    private String resultProperty;

    public void setSourceProperty(String sourceProperty) {
        this.sourceProperty = sourceProperty;
    }

    public void setResultProperty(String resultProperty) {
        this.resultProperty = resultProperty;
    }

    @Override
    public void execute() throws BuildException {
        if (sourceProperty == null || resultProperty == null) {
            throw new BuildException(
                "sourceProperty and resultProperty are required",
                getLocation()
            );
        }

        Project project = getProject();
        String sourceValue = project.getProperty(sourceProperty);

        if (sourceValue == null) {
            throw new BuildException(
                "Property '" + sourceProperty + "' is not defined",
                getLocation()
            );
        }

        String label = "Build: " + sourceValue.trim();
        project.setNewProperty(resultProperty, label);
        log("Created property '" + resultProperty + "'");
    }
}
```

Build file:

```xml
<property name="release.version" value="2.3.0" />

<target name="show-label">
    <buildLabel sourceProperty="release.version"
                resultProperty="build.label" />
    <echo message="${build.label}" />
</target>
```

Kết quả log:

```text
Build: 2.3.0
```

Nếu `build.label` đã được đặt trước khi task chạy, `setNewProperty()` không thay thế giá trị đó. Nếu task cần báo rằng kết quả không được ghi vì property đã tồn tại, có thể đọc giá trị trước bằng `getProperty()` và xử lý theo chính sách của task.

### 4.2. Khi nào không nên xuất property?

Không nên đưa mọi kết quả trung gian vào property. Property phù hợp với chuỗi cấu hình hoặc kết quả nhỏ cần dùng lại ở các task sau. Với dữ liệu lớn, danh sách phần tử phức tạp hoặc trạng thái cần thay đổi, hãy dùng file, datatype hoặc reference.

Property cũng không nên chứa mật khẩu, token bí mật hoặc nội dung nhạy cảm nếu chúng có thể bị in ra log hoặc được mở rộng trong thông báo lỗi.

## 5. Mở rộng property bằng `replaceProperties()`

Trong build file, Ant thường thay `${property.name}` trước khi gọi setter của custom task. Ví dụ:

```xml
<echo message="Version: ${release.version}" />
```

Custom task nhận giá trị đã được mở rộng nếu thuộc tính XML được Ant cấu hình theo quy trình thông thường.

Đôi khi task nhận một chuỗi được tạo trong lúc chạy và cần mở rộng property sau đó. Khi ấy có thể gọi:

```java
String expanded = getProject().replaceProperties(
    "release=${release.version};env=${deploy.environment}"
);
```

Nếu project có hai property tương ứng, kết quả sẽ chứa các giá trị đã phân giải.

Ví dụ setter nhận template:

```java
private String message;

public void setMessage(String message) {
    this.message = message;
}

@Override
public void execute() {
    String expanded = getProject().replaceProperties(message);
    log(expanded);
}
```

Build file:

```xml
<property name="release.version" value="2.3.0" />
<showMessage message="Preparing release ${release.version}" />
```

Trong trường hợp này, Ant thường đã mở rộng giá trị trước khi gọi setter. `replaceProperties()` vẫn hữu ích nếu chuỗi được task tạo hoặc nhận từ nguồn khác sau giai đoạn cấu hình.

Không nên mở rộng một chuỗi nếu cú pháp `${...}` cần được giữ nguyên cho một công cụ khác, ví dụ template cấu hình runtime. Việc thay placeholder phải phù hợp với mục tiêu của task.

## 6. Truy cập reference bằng `Project.getReference()`

Property chứa giá trị dạng chuỗi. Reference lưu một đối tượng Ant có thể được nhiều task dùng chung. Ví dụ thường gặp là `Path`, `FileSet`, `Mapper` hoặc một datatype do custom task tạo ra.

Build file khai báo path:

```xml
<path id="compile.classpath">
    <pathelement location="lib/commons-lang3.jar" />
    <pathelement location="lib/logging-api.jar" />
</path>
```

Custom task lấy reference theo ID:

```java
Object value = getProject().getReference("compile.classpath");
```

Phương thức trả về `Object`, vì reference có thể trỏ đến nhiều loại datatype khác nhau. Task phải kiểm tra `null` và kiểu thực tế trước khi ép kiểu.

### 6.1. Kiểm tra reference trước khi ép kiểu

```java
Object value = getProject().getReference("compile.classpath");

if (value == null) {
    throw new BuildException(
        "Reference 'compile.classpath' is not defined",
        getLocation()
    );
}

if (!(value instanceof org.apache.tools.ant.types.Path)) {
    throw new BuildException(
        "Reference 'compile.classpath' must be an Ant Path",
        getLocation()
    );
}

org.apache.tools.ant.types.Path classpath =
    (org.apache.tools.ant.types.Path) value;

log("Compile classpath: " + classpath.toString());
```

Kiểm tra kiểu giúp lỗi cấu hình được báo bằng thông điệp rõ ràng. Nếu ép kiểu trực tiếp mà reference thực tế không phải `Path`, task có thể ném `ClassCastException`, khiến thông báo khó hiểu hơn.

### 6.2. Truyền reference ID vào custom task

Không nên cố định tên reference trong Java nếu task có thể tái sử dụng với nhiều path. Hãy nhận ID qua thuộc tính XML:

```java
private String pathRef;

public void setPathRef(String pathRef) {
    this.pathRef = pathRef;
}
```

Sau đó:

```java
Object value = getProject().getReference(pathRef);
```

Build file:

```xml
<path id="compile.classpath">
    <pathelement location="lib/commons-lang3.jar" />
</path>

<inspectPath pathRef="compile.classpath" />
```

Ant ánh xạ `pathRef` tới setter `setPathRef(...)`. Task có thể sử dụng nhiều reference khác nhau mà không cần sửa mã Java.

## 7. Làm việc với `Path` reference

`org.apache.tools.ant.types.Path` là datatype biểu diễn một classpath hoặc danh sách đường dẫn theo cách Ant hiểu. Path có thể chứa file, thư mục, path element khác hoặc reference tới path đã khai báo.

Ví dụ build file:

```xml
<path id="compile.classpath">
    <pathelement location="lib/a.jar" />
    <pathelement location="lib/b.jar" />
</path>

<path id="runtime.classpath">
    <pathelement location="build/classes" />
    <path refid="compile.classpath" />
</path>
```

Custom task:

```java
import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;
import org.apache.tools.ant.types.Path;

public class InspectPathTask extends Task {
    private String pathRef;

    public void setPathRef(String pathRef) {
        this.pathRef = pathRef;
    }

    @Override
    public void execute() throws BuildException {
        if (pathRef == null || pathRef.trim().isEmpty()) {
            throw new BuildException("Attribute pathRef is required", getLocation());
        }

        Object reference = getProject().getReference(pathRef);
        if (!(reference instanceof Path)) {
            throw new BuildException(
                "Reference '" + pathRef + "' is missing or is not a Path",
                getLocation()
            );
        }

        Path path = (Path) reference;
        log("Path reference '" + pathRef + "': " + path);
    }
}
```

`Path.toString()` cung cấp biểu diễn đường dẫn mà Ant đang quản lý. Nếu cần duyệt từng phần tử, `Path` còn cung cấp API liệt kê các phần tử đường dẫn; hãy dùng API của `Path` thay vì tự phân tách chuỗi theo dấu `:` hoặc `;`, vì dấu phân cách phụ thuộc hệ điều hành.

### 7.1. Không giả định mọi reference là `Path`

Reference ID là tên do build file hoặc task đặt. Cùng một cơ chế `getReference()` có thể trả về `FileSet`, `FileList`, `Mapper`, `Path` hoặc một object tùy chỉnh. Vì vậy:

- Tài liệu task cần nêu rõ kiểu reference mà nó yêu cầu.
- Mã task phải kiểm tra kiểu trước khi dùng.
- Thông báo lỗi nên ghi ID và kiểu mong đợi.
- Không ép mọi reference thành chuỗi rồi xử lý thủ công.

## 8. Đăng ký reference từ custom task

Custom task cũng có thể tạo một đối tượng rồi đăng ký nó vào project để task sau tham chiếu.

Ví dụ, task tạo một `Path` và đăng ký dưới ID được người dùng chỉ định:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;
import org.apache.tools.ant.types.Path;

public class CreatePathTask extends Task {
    private String id;
    private String location;

    public void setId(String id) {
        this.id = id;
    }

    public void setLocation(String location) {
        this.location = location;
    }

    @Override
    public void execute() throws BuildException {
        if (id == null || id.trim().isEmpty()) {
            throw new BuildException("Attribute id is required", getLocation());
        }
        if (location == null || location.trim().isEmpty()) {
            throw new BuildException("Attribute location is required", getLocation());
        }

        Project project = getProject();
        Path path = new Path(project);
        path.setLocation(project.resolveFile(location));

        if (project.getReference(id) != null) {
            throw new BuildException(
                "Reference '" + id + "' already exists",
                getLocation()
            );
        }

        project.addReference(id, path);
        log("Registered Path reference '" + id + "'");
    }
}
```

Build file có thể dùng reference sau khi task đã chạy:

```xml
<target name="prepare-path">
    <createPath id="generated.path" location="build/generated" />
    <path id="compile.classpath">
        <path refid="generated.path" />
        <pathelement location="lib/api.jar" />
    </path>
</target>
```

Reference phải được tạo trước khi task khác sử dụng. Vì target được thực thi theo thứ tự, hãy khai báo `depends` hoặc gọi task tạo reference trước task tiêu thụ nó.

### 8.1. Không ghi đè reference không thuộc quyền sở hữu của task

Reference ID là một phần giao tiếp giữa các task. Nếu custom task ghi đè reference đã tồn tại, task khác có thể nhận một object khác với dự kiến.

Nên:

- Dùng namespace hoặc tiền tố riêng cho reference do task tạo.
- Kiểm tra ID đã tồn tại trước khi đăng ký.
- Ghi rõ kiểu object được lưu dưới reference.
- Tránh thay đổi object dùng chung nếu không có hợp đồng rõ ràng.

## 9. Vị trí lỗi bằng `getLocation()`

Khi custom task phát hiện cấu hình không hợp lệ, thông báo lỗi nên chỉ ra phần tử XML đã tạo ra task. Ant cung cấp thông tin đó qua `getLocation()`.

Ví dụ:

```java
if (propertyName == null) {
    throw new BuildException(
        "Attribute propertyName is required",
        getLocation()
    );
}
```

Nếu task được gọi ở dòng 18 của `build.xml`, Ant có thể hiển thị lỗi gắn với file và dòng tương ứng, thay vì chỉ in một thông báo chung.

### 9.1. `BuildException` có location

`BuildException` là loại exception Ant dùng để biểu diễn lỗi build. Có thể truyền message và location:

```java
throw new BuildException("Invalid deployment environment", getLocation());
```

Nếu lỗi gốc là một exception khác, hãy giữ nguyên cause:

```java
try {
    int port = Integer.parseInt(rawPort);
} catch (NumberFormatException ex) {
    throw new BuildException(
        "Property server.port must be an integer: " + rawPort,
        ex,
        getLocation()
    );
}
```

Việc giữ cause giúp người dùng biết lỗi chuyển đổi thực tế, còn location chỉ ra vị trí task được cấu hình.

### 9.2. Vì sao không nên chỉ ném `IllegalArgumentException`?

Đoạn code sau có thể hoạt động như exception Java thông thường:

```java
throw new IllegalArgumentException("Missing property");
```

Nhưng nó không thể hiện rõ đây là lỗi cấu hình build và không tự gắn vị trí XML của task. Với lỗi do người dùng cấu hình custom task, nên dùng `BuildException` và truyền `getLocation()`.

`IllegalArgumentException` vẫn có thể được dùng nội bộ trong các lớp Java độc lập. Khi exception thoát ra khỏi `execute()`, hãy chuyển thành `BuildException` có thông điệp và location phù hợp.

### 9.3. `getLocation()` khác stack trace như thế nào?

- `getLocation()` chỉ vị trí trong build file nơi task được khai báo hoặc cấu hình.
- Stack trace chỉ các lời gọi phương thức Java dẫn đến lỗi.

Hai thông tin bổ sung cho nhau. Với lỗi cấu hình, location giúp người dùng mở đúng dòng XML. Với lỗi lập trình hoặc lỗi thư viện, stack trace giúp lập trình viên xác định vị trí trong mã Java.

## 10. Ghi log đúng cấp độ

Custom task nên dùng cơ chế log của Ant thay vì `System.out.println()` hoặc `System.err.println()`.

Các cấp độ log phổ biến:

| Cấp độ | Hằng số | Khi dùng |
|---|---|---|
| Error | `Project.MSG_ERR` | Thông tin lỗi nghiêm trọng. |
| Warning | `Project.MSG_WARN` | Cấu hình đáng ngờ hoặc điều kiện có thể gây vấn đề. |
| Info | `Project.MSG_INFO` | Thông tin vận hành bình thường. |
| Verbose | `Project.MSG_VERBOSE` | Chi tiết bổ sung khi người dùng yêu cầu log nhiều hơn. |
| Debug | `Project.MSG_DEBUG` | Thông tin phục vụ điều tra sâu. |

Ví dụ:

```java
log("Starting custom task", Project.MSG_INFO);
log("Optional property is not set", Project.MSG_WARN);
log("Resolved path: " + path, Project.MSG_VERBOSE);
```

Ant có thể lọc thông báo theo mức log được người dùng chọn. Nếu dùng `System.out`, task bỏ qua cơ chế này và có thể làm log CI khó đọc.

Không nên log giá trị nhạy cảm như password, access token hoặc secret property. Nếu cần xác nhận một secret đã được cấu hình, chỉ log trạng thái có/không mà không in giá trị.

## 11. Ví dụ hoàn chỉnh: đọc property, reference và báo lỗi có location

Ví dụ này kết hợp các API vừa học. Custom task `InspectBuildContext`:

- Nhận tên property cần đọc.
- Nhận ID của một `Path` reference.
- Ghi thông tin project, property và path.
- Có thể tạo một property kết quả.
- Báo lỗi bằng `BuildException` gắn `getLocation()`.

### 11.1. Mã Java

Tạo tệp `src/custom/java/com/example/ant/InspectBuildContext.java`:

```java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;
import org.apache.tools.ant.types.Path;

public class InspectBuildContext extends Task {
    private String propertyName;
    private String pathRef;
    private String resultProperty;

    public void setPropertyName(String propertyName) {
        this.propertyName = propertyName;
    }

    public void setPathRef(String pathRef) {
        this.pathRef = pathRef;
    }

    public void setResultProperty(String resultProperty) {
        this.resultProperty = resultProperty;
    }

    @Override
    public void execute() throws BuildException {
        Project project = getProject();
        if (project == null) {
            throw new BuildException(
                "Task is not attached to an Ant Project",
                getLocation()
            );
        }

        if (propertyName == null || propertyName.trim().isEmpty()) {
            throw new BuildException(
                "Attribute propertyName is required",
                getLocation()
            );
        }

        if (pathRef == null || pathRef.trim().isEmpty()) {
            throw new BuildException(
                "Attribute pathRef is required",
                getLocation()
            );
        }

        String value = project.getProperty(propertyName);
        if (value == null) {
            throw new BuildException(
                "Property '" + propertyName + "' is not defined",
                getLocation()
            );
        }

        Object reference = project.getReference(pathRef);
        if (reference == null) {
            throw new BuildException(
                "Reference '" + pathRef + "' is not defined",
                getLocation()
            );
        }

        if (!(reference instanceof Path)) {
            throw new BuildException(
                "Reference '" + pathRef + "' must be an Ant Path",
                getLocation()
            );
        }

        Path path = (Path) reference;
        String summary = "project=" + project.getName()
            + "; property=" + propertyName + "=" + value
            + "; path=" + path;

        log("Project: " + project.getName(), Project.MSG_INFO);
        log("Property: " + propertyName + "=" + value, Project.MSG_INFO);
        log("Reference: " + pathRef + "=" + path, Project.MSG_VERBOSE);

        if (resultProperty != null && !resultProperty.trim().isEmpty()) {
            project.setNewProperty(resultProperty, summary);
        }
    }
}
```

### 11.2. Build file

```xml
<project name="inspect-context-demo" default="run" basedir=".">
    <property name="release.version" value="2.3.0" />
    <property name="build.environment" value="development" />

    <path id="compile.classpath">
        <pathelement location="lib/commons-lang3.jar" />
        <pathelement location="lib/logging-api.jar" />
    </path>

    <taskdef name="inspectBuildContext"
             classname="com.example.ant.InspectBuildContext"
             classpath="build/custom-tasks.jar" />

    <target name="run">
        <inspectBuildContext propertyName="release.version"
                             pathRef="compile.classpath"
                             resultProperty="build.context.summary" />

        <echo message="${build.context.summary}" />
    </target>
</project>
```

Khi target `run` được thực thi, Ant truyền project hiện tại cho task. Task đọc `release.version`, lấy `compile.classpath` theo reference ID, kiểm tra đó là một `Path`, ghi log và xuất `build.context.summary` để task `<echo>` sử dụng.

### 11.3. Biên dịch và đóng gói custom task

Custom task cần được biên dịch với `ant.jar` trên classpath vì lớp sử dụng `Task`, `Project`, `BuildException` và `Path`.

Ví dụ lệnh trên môi trường Unix-like, giả sử `ANT_HOME` đã được đặt:

```bash
mkdir -p build/custom-classes
javac -cp "$ANT_HOME/lib/ant.jar" \
      -d build/custom-classes \
      src/custom/java/com/example/ant/InspectBuildContext.java
jar cf build/custom-tasks.jar -C build/custom-classes .
```

Trên Windows, dùng đường dẫn `ant.jar` tương ứng trong thư mục cài Ant, ví dụ `%ANT_HOME%\lib\ant.jar`, và cú pháp lệnh phù hợp với Command Prompt hoặc PowerShell.

Khi chạy build file, Ant đã có các lớp lõi của chính nó trên classpath. JAR custom task chỉ cần được cung cấp qua `taskdef` cùng các dependency bổ sung mà task thực sự sử dụng.

## 12. Cách xử lý lỗi trong custom task

Custom task nên phân biệt lỗi cấu hình, lỗi dữ liệu đầu vào và lỗi hệ thống.

### 12.1. Lỗi cấu hình build file

Ví dụ:

- Thiếu thuộc tính bắt buộc.
- Property được yêu cầu chưa được khai báo.
- Reference ID không tồn tại.
- Reference có kiểu không đúng.
- Giá trị số hoặc boolean không hợp lệ.

Với những lỗi này, dùng `BuildException` và `getLocation()` để người dùng biết lỗi đến từ phần tử task nào.

```java
if (pathRef == null) {
    throw new BuildException("Attribute pathRef is required", getLocation());
}
```

### 12.2. Lỗi I/O hoặc lỗi thư viện

Nếu custom task đọc file hoặc gọi API có thể ném exception, hãy giữ nguyên nguyên nhân:

```java
try {
    // Thực hiện thao tác I/O.
} catch (java.io.IOException ex) {
    throw new BuildException(
        "Unable to read the configured input file",
        ex,
        getLocation()
    );
}
```

Không nên bắt `Exception` rồi chỉ log một dòng và tiếp tục như thể task thành công. Điều đó có thể khiến các target sau dùng đầu ra chưa hoàn chỉnh.

### 12.3. Cảnh báo không làm build thất bại

Nếu một điều kiện không bắt buộc, có thể ghi warning:

```java
if (optionalValue == null) {
    log("Optional property is not set; using the default behavior",
        Project.MSG_WARN);
}
```

Chỉ dùng warning khi task thực sự có cách tiếp tục hợp lệ. Nếu thiếu cấu hình khiến kết quả không thể đúng, hãy ném `BuildException`.

## 13. Những lưu ý về vòng đời và khả năng tái sử dụng task

Ant cấu hình một đối tượng task rồi gọi `execute()`. Trong một số tình huống, cùng một instance có thể được tái sử dụng hoặc cấu hình lại theo cách mà task không nên giả định trạng thái luôn mới.

Các nguyên tắc hữu ích:

- Lưu giá trị setter vào field đơn giản; kiểm tra chúng trong `execute()`.
- Không giữ `Project` của một lần build trong biến static.
- Không chia sẻ trạng thái mutable giữa các task không liên quan.
- Khởi tạo lại dữ liệu tạm ở thời điểm phù hợp.
- Không thực hiện công việc nặng trong setter; setter nên chủ yếu lưu cấu hình.
- Không phụ thuộc vào thứ tự setter được Ant gọi.
- Báo lỗi bằng thông điệp rõ ràng và location.

Nếu task cần hỗ trợ nhiều lần cấu hình trên cùng một instance hoặc có nested element phức tạp, hãy xem xét các hook vòng đời phù hợp như `init()` hoặc `execute()` và cách Ant tạo/cấu hình task. Với custom task đơn giản, đặt xử lý chính trong `execute()` thường dễ hiểu nhất.

## 14. Kiểm thử custom task

Vì custom task phụ thuộc `Project`, test đơn vị có thể tạo một project Ant, gắn project vào task rồi gọi `execute()`.

Ví dụ minh họa:

```java
import org.apache.tools.ant.Project;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BuildLabelTaskTest {
    @Test
    void readsProjectPropertyAndCreatesResult() {
        Project project = new Project();
        project.init();
        project.setNewProperty("release.version", "2.3.0");

        BuildLabelTask task = new BuildLabelTask();
        task.setProject(project);
        task.setSourceProperty("release.version");
        task.setResultProperty("build.label");

        task.execute();

        assertEquals("Build: 2.3.0", project.getProperty("build.label"));
    }
}
```

Trong test, `setProject(project)` mô phỏng bước Ant gắn ngữ cảnh project. Nếu task cần location cụ thể, có thể cấu hình location bằng API tương ứng trong test hoặc kiểm tra thông điệp lỗi theo cách phù hợp.

Nên kiểm tra ít nhất các tình huống:

- Property tồn tại và có giá trị hợp lệ.
- Property chưa được khai báo.
- Reference tồn tại và đúng kiểu.
- Reference không tồn tại.
- Reference tồn tại nhưng sai kiểu.
- Thuộc tính bắt buộc bị bỏ trống.
- Property kết quả đã tồn tại trước khi task chạy.

Ngoài unit test, nên có một build file mẫu chạy task qua Ant thật để kiểm tra việc `taskdef`, setter mapping, property expansion và location hoạt động trong ngữ cảnh thực tế.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `getProject()` trả về `null` | Task được tạo trực tiếp trong Java mà chưa gọi `setProject()`. | Chạy task qua Ant hoặc gắn một `Project` trong test. |
| `getProperty()` trả về `null` | Tên sai hoặc property chưa được khai báo trước khi task chạy. | Kiểm tra tên property và thứ tự target/task. |
| Giá trị property không thay đổi sau `setNewProperty()` | Property đã được đặt trước đó; Ant property có tính bất biến. | Dùng tên property mới hoặc chọn cơ chế lưu trạng thái khác. |
| `getUserProperty()` trả về `null` nhưng `getProperty()` có giá trị | Property được đặt trong build file, không phải user property. | Dùng `getProperty()` nếu chỉ cần giá trị hiệu lực. |
| `getReference()` trả về `null` | ID chưa được khai báo hoặc task chạy trước bước tạo reference. | Kiểm tra `id`, `refid` và dependency giữa các target. |
| `ClassCastException` khi đọc reference | Reference thực tế không phải kiểu task giả định. | Kiểm tra `instanceof` và báo kiểu mong đợi bằng `BuildException`. |
| Task không tìm thấy property trong build con | Project con có ngữ cảnh riêng hoặc property không được truyền xuống. | Truyền property qua nested `<property>` hoặc cấu hình kế thừa phù hợp. |
| Lỗi không chỉ ra dòng build file | Ném exception không kèm `getLocation()`. | Dùng constructor `BuildException` có location. |
| Log không theo mức Ant | Dùng `System.out.println()` hoặc `System.err.println()`. | Dùng `log(message, Project.MSG_...)`. |
| Property `${...}` vẫn còn nguyên | Property không tồn tại hoặc chuỗi chưa được mở rộng ở giai đoạn phù hợp. | Kiểm tra tên và dùng `replaceProperties()` khi cần mở rộng động. |
| Custom task ghi đè reference của task khác | Dùng ID chung hoặc không kiểm tra reference đã tồn tại. | Dùng ID có namespace và kiểm tra trước `addReference()`. |

## 16. Bài thực hành

Tạo một custom task có tên `InspectBuildContext` với các yêu cầu:

1. Kế thừa `org.apache.tools.ant.Task`.
2. Nhận thuộc tính `propertyName` để xác định property cần đọc.
3. Nhận thuộc tính `pathRef` để xác định reference cần lấy.
4. Nhận thuộc tính tùy chọn `resultProperty` để xuất một chuỗi tóm tắt.
5. Dùng `getProject()` để lấy project hiện tại.
6. Đọc property bằng `Project.getProperty()` và báo lỗi nếu property bắt buộc không tồn tại.
7. Đọc reference bằng `Project.getReference()` và xác nhận object là `Path`.
8. Ghi tên project, giá trị property và path bằng `log()`.
9. Nếu có `resultProperty`, gọi `setNewProperty()` để xuất kết quả.
10. Mọi lỗi cấu hình phải dùng `BuildException` kèm `getLocation()`.

Build file thử nghiệm:

```xml
<project name="custom-task-lab" default="run" basedir=".">
    <property name="app.version" value="1.5.0" />

    <path id="app.classpath">
        <pathelement location="lib/example.jar" />
    </path>

    <taskdef name="inspectBuildContext"
             classname="com.example.ant.InspectBuildContext"
             classpath="build/custom-tasks.jar" />

    <target name="run">
        <inspectBuildContext propertyName="app.version"
                             pathRef="app.classpath"
                             resultProperty="context.summary" />
        <echo message="${context.summary}" />
    </target>
</project>
```

Sau khi chạy thành công, thử các tình huống:

- Đổi `propertyName` thành một tên chưa khai báo.
- Đổi `pathRef` thành một ID không tồn tại.
- Tham chiếu một object không phải `Path`.
- Bỏ `propertyName` hoặc `pathRef`.
- Khai báo `context.summary` trước khi task chạy và quan sát quy tắc bất biến của property.
- Chạy task từ một target khác và xem location trong thông báo lỗi.

### Câu hỏi tự kiểm tra

1. Vì sao custom task thường kế thừa `Task`?
2. `getProject()` trả về đối tượng nào?
3. `Project.getProperty()` trả về gì khi property chưa được khai báo?
4. Khác biệt giữa `getProperty()` và `getUserProperty()` là gì?
5. Vì sao `setNewProperty()` không ghi đè giá trị đã tồn tại?
6. `Project.getReference()` trả về kiểu dữ liệu nào?
7. Vì sao cần kiểm tra `instanceof` trước khi ép reference thành `Path`?
8. `getLocation()` cung cấp thông tin gì?
9. Vì sao nên ném `BuildException` thay vì chỉ ném `IllegalArgumentException` cho lỗi cấu hình task?
10. Vì sao custom task nên dùng `log()` thay cho `System.out.println()`?

### Đáp án gợi ý

- `Task` cung cấp vòng đời thực thi và ngữ cảnh Ant như project, location và logging.
- Project mà Ant đã gắn cho task đang chạy.
- `null`.
- `getProperty()` lấy giá trị property hiệu lực; `getUserProperty()` chỉ lấy giá trị được đặt như user property.
- Ant property thông thường bất biến sau khi đã đặt; `setNewProperty()` chỉ đặt khi tên chưa có giá trị.
- `Object`, vì reference có thể chứa nhiều loại datatype.
- Để tránh `ClassCastException` và báo lỗi cấu hình rõ ràng.
- Vị trí phần tử task trong build file, thường gồm tên file và số dòng.
- `BuildException` thể hiện lỗi build và có thể gắn location của task.
- `log()` tuân theo mức log và cơ chế logging của Ant, phù hợp với terminal và CI.

## Kết luận

Custom task có thể dùng `getProject()` để truy cập project hiện tại, đọc property bằng `getProperty()`, tạo kết quả mới bằng `setNewProperty()` và lấy datatype dùng chung bằng `getReference()`. Vì reference trả về `Object`, task cần kiểm tra kiểu trước khi sử dụng. Khi cấu hình không hợp lệ, hãy ném `BuildException` có kèm `getLocation()` để Ant chỉ đúng dòng build file. Kết hợp các API này với `log()` giúp custom task hòa nhập vào hệ thống Ant, tái sử dụng được giữa nhiều dự án và dễ điều tra khi build thất bại.
