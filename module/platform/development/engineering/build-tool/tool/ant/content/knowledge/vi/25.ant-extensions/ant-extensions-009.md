# Ghi log và ném BuildException có thông tin hữu ích

Khi mở rộng Apache Ant bằng custom task, cách task ghi log và báo lỗi ảnh hưởng trực tiếp tới khả năng chẩn đoán build. Một task có thể chạy đúng khi mọi đầu vào hợp lệ, nhưng khi thiếu file, sai cấu hình hoặc gặp lỗi I/O, thông báo chung chung như `Build failed` không giúp người dùng biết phải sửa gì.

Ant cung cấp hai cơ chế chính cho custom task:

- **Logging API** của `Task` để ghi thông tin theo mức độ: error, warning, info, verbose và debug.
- **`BuildException`** để báo rằng task không thể hoàn thành và làm build thất bại. Có thể gắn vị trí task trong build file và giữ exception gốc để người dùng lần theo nguyên nhân.

Một task tốt phân biệt rõ thông tin tiến độ, cảnh báo có thể tiếp tục và lỗi khiến build không thể an toàn đi tiếp. Khi thất bại, nó cung cấp ngữ cảnh đủ cụ thể: task đang làm gì, file hoặc cấu hình nào liên quan, giá trị nào sai, vì sao sai và người dùng nên kiểm tra điều gì.

## 1. Logging trong custom Ant Task

Custom task thường kế thừa `org.apache.tools.ant.Task`. Lớp này kế thừa logging API từ `ProjectComponent`, vì vậy có thể gọi `log(...)` trực tiếp trong task.

Hai cách gọi thường dùng:

~~~java
log("Starting configuration validation");
log("Scanning optional metadata", Project.MSG_VERBOSE);
~~~

`log(String)` ghi thông điệp ở mức INFO. Overload `log(String, int)` cho phép chọn mức cụ thể bằng các hằng số của `Project`.

Các mức logging chuẩn:

| Hằng số | Ý nghĩa | Nội dung phù hợp |
|---|---|---|
| `Project.MSG_ERR` | Error | Lỗi cần được chú ý; thường task sẽ ném `BuildException` nếu không thể tiếp tục |
| `Project.MSG_WARN` | Warning | Điều kiện bất thường nhưng task vẫn có thể tiếp tục an toàn |
| `Project.MSG_INFO` | Information | Tiến độ hoặc kết quả chính mà người chạy build cần biết |
| `Project.MSG_VERBOSE` | Verbose | Chi tiết thực thi hữu ích khi điều tra build |
| `Project.MSG_DEBUG` | Debug | Thông tin nội bộ sâu hơn dành cho chẩn đoán |

Các hằng số này được định nghĩa trong `org.apache.tools.ant.Project`. Nên dùng hằng số thay vì ghi số nguyên trực tiếp để người đọc hiểu ý nghĩa của mức log.

Ví dụ:

~~~java
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

public class ReportTask extends Task {
    @Override
    public void execute() {
        log("Preparing report", Project.MSG_INFO);
        log("Using report template: templates/report.xml", Project.MSG_VERBOSE);
        log("Resolved 12 input files", Project.MSG_DEBUG);
        log("Optional metadata file was not found; continuing", Project.MSG_WARN);
    }
}
~~~

Thông điệp INFO xuất hiện trong lần chạy Ant thông thường. VERBOSE và DEBUG thường chỉ hiển thị khi người dùng yêu cầu log chi tiết hơn. Nhờ đó, build thường ngày không bị ngập bởi thông tin nội bộ, nhưng vẫn có dữ liệu khi cần điều tra.

## 2. Chọn mức log phù hợp

Một quy ước đơn giản giúp log nhất quán:

- Dùng INFO cho các bước chính: bắt đầu xử lý, hoàn tất, số lượng file hoặc artifact được tạo.
- Dùng WARN cho tình huống đáng chú ý nhưng có phương án fallback an toàn.
- Dùng VERBOSE cho đường dẫn, lựa chọn cấu hình và các bước trung gian.
- Dùng DEBUG cho dữ liệu chẩn đoán chi tiết, quyết định nội bộ hoặc giá trị tính toán.
- Dùng ERROR khi task thực sự muốn ghi một lỗi nhưng vẫn tiếp tục theo một chính sách rõ ràng. Nếu task không thể hoàn thành, thường nên ném `BuildException` để Ant quản lý trạng thái thất bại.

Ví dụ một task có file metadata tùy chọn:

~~~java
if (metadataFile.isFile()) {
    log("Loading metadata from " + metadataFile, Project.MSG_VERBOSE);
    loadMetadata(metadataFile);
} else {
    log("Optional metadata file not found: " + metadataFile
        + "; default metadata will be used", Project.MSG_WARN);
}
~~~

Ở đây thiếu metadata không phải lỗi fatal vì task có default. Warning nói rõ file nào thiếu và task sẽ làm gì tiếp theo.

Ngược lại, nếu file cấu hình bắt buộc không tồn tại, task không nên chỉ ghi warning rồi tiếp tục với cấu hình rỗng. Nó nên ném `BuildException` với thông tin đủ rõ để người dùng sửa đầu vào.

### 2.1. Logging chịu ảnh hưởng bởi mức verbosity của Ant

Người chạy có thể thay đổi lượng log được hiển thị qua command line:

~~~bash
ant validate
ant -verbose validate
ant -debug validate
ant -quiet validate
~~~

- Chạy mặc định thường hiển thị thông tin ở mức INFO trở lên.
- `-verbose` hiển thị thêm thông tin VERBOSE.
- `-debug` bật mức DEBUG chi tiết hơn.
- `-quiet` giảm lượng thông tin, chỉ giữ các thông báo quan trọng theo cấu hình logger.

Task không nên tự kiểm tra đối số command line để quyết định có log hay không. Hãy luôn ghi đúng mức; Ant listener/logger chịu trách nhiệm lọc theo verbosity mà người dùng chọn.

### 2.2. Không dùng `System.out.println` cho log của task

Trong custom task, ưu tiên:

~~~java
log("Compiled 24 source files", Project.MSG_INFO);
~~~

thay vì:

~~~java
System.out.println("Compiled 24 source files");
~~~

Logging API giúp thông điệp đi qua cơ chế logger/listener của Ant, có mức độ và được tích hợp với output của build. `System.out` hoặc `System.err` bỏ qua phân loại log và có thể làm output khó kiểm soát trong CI hoặc khi Ant được nhúng vào một ứng dụng khác.

Cũng không nên dùng `printStackTrace()` để tự ghi exception. Hãy giữ exception gốc làm cause của `BuildException`; Ant sẽ xử lý hiển thị lỗi theo cơ chế của nó.

## 3. `BuildException` dùng để làm gì?

`BuildException` là exception của Ant dùng để báo lỗi trong quá trình thực hiện task hoặc build. Custom task thường ném nó từ phương thức `execute()` khi không thể tiếp tục.

~~~java
import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class ValidateTask extends Task {
    @Override
    public void execute() throws BuildException {
        if (/* input is invalid */ false) {
            throw new BuildException("Required input is invalid");
        }
    }
}
~~~

Khi task ném `BuildException`, Ant đánh dấu việc thực hiện task/target là thất bại. Các target phụ thuộc vào target thất bại sẽ không được thực hiện như thể build đã thành công. Đây là cách một custom task báo cho build engine biết rằng điều kiện cần thiết không được đáp ứng.

`BuildException` phù hợp với các lỗi như:

- Thiếu attribute bắt buộc hoặc cấu hình không hợp lệ.
- File đầu vào bắt buộc không tồn tại hoặc không đọc được.
- Nội dung cấu hình không đáp ứng quy tắc mà task yêu cầu.
- Công cụ ngoài trả về trạng thái lỗi mà task không thể khắc phục.
- Artifact đầu ra không thể tạo hoặc không thể ghi.
- Một điều kiện tiên quyết không đạt và tiếp tục sẽ tạo kết quả không đáng tin cậy.

Không nên dùng `BuildException` cho một điều kiện bình thường mà task có thể xử lý theo thiết kế, ví dụ file cache tùy chọn không tồn tại nhưng task có thể tạo lại cache.

## 4. Gắn vị trí lỗi bằng `getLocation()`

Một trong những thông tin hữu ích nhất của `BuildException` là vị trí task trong build file. `Task` kế thừa phương thức `getLocation()` từ `ProjectComponent`; phương thức này trả về `Location` mà Ant gán cho task khi đọc build file.

Có thể truyền location vào constructor của `BuildException`:

~~~java
throw new BuildException(
    "Required attribute 'file' is missing",
    getLocation()
);
~~~

Khi đó, Ant có thể hiển thị lỗi kèm file build và số dòng tương ứng, thay vì chỉ đưa ra một thông điệp không có vị trí.

Ví dụ build file:

~~~xml
<target name="validate-config">
    <validateConfig file="config/app.properties"/>
</target>
~~~

Nếu task thất bại, location giúp người dùng tìm tới phần tử `<validateConfig>` trong `build.xml` để kiểm tra cấu hình.

### 4.1. Vì sao không nên tự ghép số dòng vào message?

Không nên viết:

~~~java
throw new BuildException("Error at build.xml line 18: invalid config");
~~~

Số dòng có thể thay đổi khi build file được chỉnh sửa, và task không nên tự đoán vị trí. Hãy để Ant cung cấp `getLocation()` cho exception:

~~~java
throw new BuildException("Invalid configuration file: " + configFile,
                         getLocation());
~~~

Cách này giúp thông báo gắn với đúng nơi task được khai báo trong build file.

## 5. Giữ nguyên nguyên nhân gốc bằng exception cause

Khi gọi API Java hoặc đọc file, task có thể gặp `IOException`, `ParserConfigurationException`, `SAXException` hoặc exception của thư viện khác. Không nên bỏ mất nguyên nhân bằng cách chỉ ném một thông báo mới.

`BuildException` có constructor nhận message, cause và location:

~~~java
try {
    loadConfiguration(configFile);
} catch (IOException ex) {
    throw new BuildException(
        "Unable to read configuration file '" + configFile + "'",
        ex,
        getLocation()
    );
}
~~~

Exception gốc `ex` được giữ làm cause. Khi cần xem chi tiết, người dùng có thể đọc nguyên nhân thấp hơn thay vì chỉ thấy thông báo tổng quát của task.

Một số constructor hữu ích của `BuildException`:

~~~java
new BuildException("Message");
new BuildException("Message", getLocation());
new BuildException(cause, getLocation());
new BuildException("Message", cause, getLocation());
~~~

Khi đã có ngữ cảnh nghiệp vụ, nên dùng constructor có message, cause và location. Message giải thích thao tác thất bại; cause giữ lỗi kỹ thuật ban đầu; location chỉ ra nơi task được gọi.

### 5.1. Không nuốt exception

Đây là cách xử lý không tốt:

~~~java
try {
    loadConfiguration(configFile);
} catch (IOException ex) {
    log("Could not load configuration", Project.MSG_WARN);
    // Continue as if configuration had been loaded.
}
~~~

Nếu cấu hình là bắt buộc, task có thể tiếp tục với trạng thái không xác định và tạo artifact sai. Nên chuyển lỗi thành `BuildException`:

~~~java
try {
    loadConfiguration(configFile);
} catch (IOException ex) {
    throw new BuildException(
        "Could not load required configuration '" + configFile + "'",
        ex,
        getLocation()
    );
}
~~~

Nếu lỗi thực sự có thể bỏ qua, hãy ghi warning nói rõ fallback nào sẽ được dùng và bảo đảm task thực hiện fallback đó. Không chỉ ghi log rồi bỏ qua exception một cách chung chung.

## 6. Thiết kế thông báo lỗi hữu ích

Một thông báo lỗi tốt giúp người đọc trả lời được các câu hỏi:

1. Task đang cố làm gì?
2. Đầu vào hoặc tài nguyên nào liên quan?
3. Điều kiện nào không được đáp ứng?
4. Giá trị thực tế là gì và giá trị nào được mong đợi?
5. Người dùng nên kiểm tra hoặc sửa điều gì tiếp theo?

Ví dụ chưa đủ thông tin:

~~~text
Invalid input
~~~

Thông báo hữu ích hơn:

~~~text
Configuration file 'config/app.properties' is missing the required key 'app.name'. Add a non-empty app.name entry and run the validate target again.
~~~

Thông báo thứ hai nêu file, key bị thiếu, yêu cầu và bước sửa.

Một công thức dễ áp dụng:

~~~text
<operation> failed for <resource> because <specific reason>. <next action>.
~~~

Ví dụ:

- `Cannot create report 'build/reports/summary.xml': parent directory is not writable. Check the output directory permissions.`
- `Unsupported Java release '22' for compiler version 17. Use a supported release or select a newer compiler.`
- `No source files matched '**/*.java' under 'src/generated'. Check the source directory and include pattern.`
- `Could not start analyzer 'tools/analyzer.jar': Java executable was not found. Verify JAVA_HOME or configure the task's JVM path.`

Không đưa quá nhiều thông tin nội bộ không liên quan vào message. Mục tiêu là chỉ ra đúng điểm cần sửa, không tạo một dump khó đọc.

## 7. Ví dụ custom task hoàn chỉnh: kiểm tra file cấu hình

Ví dụ sau tạo task `validateConfig`. Task nhận attribute `file`, resolve đường dẫn tương đối theo basedir của project, kiểm tra file, đọc nội dung UTF-8 và xác nhận có property bắt buộc `app.name`.

~~~java
package com.example.ant;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Project;
import org.apache.tools.ant.Task;

public class ValidateConfigTask extends Task {
    private String file;

    public void setFile(String file) {
        this.file = file;
    }

    @Override
    public void execute() throws BuildException {
        if (file == null || file.trim().isEmpty()) {
            throw new BuildException(
                "Required attribute 'file' must be provided.",
                getLocation()
            );
        }

        File configFile = getProject().resolveFile(file);
        log("Validating configuration: " + configFile.getAbsolutePath(),
            Project.MSG_VERBOSE);

        if (!configFile.isFile()) {
            throw new BuildException(
                "Configuration file does not exist or is not a regular file: "
                    + configFile.getAbsolutePath()
                    + ". Check the file path and the project's basedir.",
                getLocation()
            );
        }

        if (!configFile.canRead()) {
            throw new BuildException(
                "Configuration file is not readable: "
                    + configFile.getAbsolutePath()
                    + ". Check file permissions.",
                getLocation()
            );
        }

        Properties properties = new Properties();
        try (Reader reader = new InputStreamReader(
                new FileInputStream(configFile), StandardCharsets.UTF_8)) {
            properties.load(reader);
        } catch (IOException ex) {
            throw new BuildException(
                "Failed to read configuration file '"
                    + configFile.getAbsolutePath()
                    + "'. Check its encoding and permissions.",
                ex,
                getLocation()
            );
        }

        String appName = properties.getProperty("app.name");
        if (appName == null || appName.trim().isEmpty()) {
            throw new BuildException(
                "Required property 'app.name' is missing or blank in '"
                    + configFile.getAbsolutePath()
                    + "'. Add a non-empty app.name entry.",
                getLocation()
            );
        }

        log("Configuration is valid for application '" + appName + "'.",
            Project.MSG_INFO);
    }
}
~~~

Các quyết định quan trọng trong task:

- Setter `setFile` nhận attribute `file` do Ant introspection ánh xạ.
- Việc kiểm tra đầu vào diễn ra trong `execute()` để exception có `getLocation()`.
- `getProject().resolveFile(file)` phân giải đường dẫn tương đối theo basedir của project.
- Log đường dẫn tuyệt đối ở mức VERBOSE để hỗ trợ chẩn đoán mà không làm output mặc định quá dài.
- Lỗi thiếu file, không đọc được hoặc thiếu key bắt buộc đều tạo `BuildException`.
- Khi đọc file gặp `IOException`, exception gốc được giữ làm cause.
- Khi thành công, task ghi một thông điệp INFO ngắn.

### 7.1. Đăng ký và gọi custom task

Sau khi biên dịch lớp task và đặt class file cùng package trong thư mục `build/ant-tasks`, có thể đăng ký bằng `<taskdef>`:

~~~xml
<project name="sample" default="validate">

    <taskdef name="validateConfig"
             classname="com.example.ant.ValidateConfigTask"
             classpath="build/ant-tasks"/>

    <target name="validate">
        <validateConfig file="config/app.properties"/>
    </target>

</project>
~~~

Nếu task có dependency JAR, classpath của `taskdef` phải bao gồm chúng. Trong dự án thực tế, task class thường được đóng gói thành JAR riêng và classpath được khai báo bằng `<path>`/`classpathref`.

File cấu hình hợp lệ:

~~~properties
app.name=Inventory Service
app.mode=production
~~~

Nếu thiếu `app.name`, task sẽ ném `BuildException` với thông tin về file và key cần bổ sung. Ant hiển thị vị trí `<validateConfig>` trong build file và đánh dấu target `validate` thất bại.

## 8. Xác thực cấu hình sớm và phân loại lỗi

Nên kiểm tra các điều kiện bắt buộc trước khi thực hiện công việc tốn thời gian hoặc tạo output một phần.

Một trình tự hợp lý:

1. Kiểm tra attribute bắt buộc.
2. Chuẩn hóa và resolve đường dẫn.
3. Kiểm tra file/thư mục đầu vào.
4. Kiểm tra quyền hoặc khả năng truy cập nếu có thể xác định.
5. Đọc và parse nội dung.
6. Kiểm tra các giá trị nghiệp vụ bắt buộc.
7. Thực hiện thao tác chính.
8. Ghi log kết quả thành công.

Có thể phân loại lỗi:

| Nhóm | Ví dụ | Hành vi phù hợp |
|---|---|---|
| Cấu hình task sai | Thiếu `file`, giá trị enum không hợp lệ | Ném `BuildException` sớm, kèm location |
| Đầu vào không hợp lệ | File thiếu key, XML sai cấu trúc | Ném `BuildException` với file và chi tiết lỗi |
| Lỗi môi trường | Không có quyền ghi, executable không tồn tại | Giữ nguyên cause nếu có và nêu cách kiểm tra |
| Điều kiện tùy chọn | Cache hoặc metadata không bắt buộc bị thiếu | Ghi WARN và dùng fallback đã định nghĩa |
| Thông tin tiến độ | Bắt đầu/hoàn tất thao tác | Ghi INFO |
| Chẩn đoán nội bộ | Đường dẫn đã resolve, số lượng item, lựa chọn algorithm | Ghi VERBOSE hoặc DEBUG |

Không nên biến mọi lỗi thành `BuildException` nếu task có thể xử lý và tiếp tục an toàn. Ngược lại, không nên hạ lỗi bắt buộc thành warning chỉ để build không đỏ.

## 9. Khi nào nên dùng `<fail>` thay cho custom `BuildException`?

Trong build file XML thuần, Ant có task `<fail>` để kết thúc build với thông báo tùy chỉnh:

~~~xml
<target name="validate-version">
    <condition property="version.present">
        <isset property="release.version"/>
    </condition>
    <fail unless="version.present"
          message="Property release.version must be provided with -Drelease.version=..."/>
</target>
~~~

`<fail>` phù hợp khi điều kiện có thể diễn đạt trực tiếp bằng task/condition của Ant. Custom task nên ném `BuildException` khi logic Java của task phát hiện lỗi trong quá trình thực hiện.

Cả hai đều làm build thất bại, nhưng thuộc về hai lớp khác nhau:

- `<fail>` là cách khai báo lỗi trong build file.
- `BuildException` là cách Java task báo lỗi cho Ant.

Không cần tạo custom task chỉ để thay thế một `<fail>` đơn giản. Hãy dùng custom task khi cần tích hợp API Java, xử lý dữ liệu phức tạp hoặc tái sử dụng logic mà XML task hiện có không biểu diễn thuận tiện.

## 10. Tránh log trùng với BuildException

Một lỗi phổ biến là vừa ghi log ERROR vừa ném exception chứa cùng một thông điệp:

~~~java
log("Configuration file is missing", Project.MSG_ERR);
throw new BuildException("Configuration file is missing", getLocation());
~~~

Kết quả có thể là cùng một lỗi xuất hiện hai lần trong console: một lần từ logger và một lần từ cơ chế báo thất bại của Ant.

Với lỗi fatal, thường chỉ cần ném `BuildException` có message tốt và location. Ant chịu trách nhiệm hiển thị lỗi. Nếu cần thêm chẩn đoán chi tiết, ghi thông tin bổ sung ở mức VERBOSE/DEBUG trước khi ném, nhưng tránh lặp nguyên văn message lỗi.

Ví dụ:

~~~java
log("Attempting to read configuration from " + configFile,
    Project.MSG_VERBOSE);

try {
    loadConfiguration(configFile);
} catch (IOException ex) {
    throw new BuildException(
        "Unable to load required configuration '" + configFile + "'",
        ex,
        getLocation()
    );
}
~~~

Không bắt `BuildException` rồi bọc lại nếu không bổ sung ngữ cảnh có ích. Nếu task có nhiều tầng xử lý, hãy để exception Ant đi lên hoặc chỉ wrap exception thư viện ở ranh giới nơi task có đủ thông tin để thêm ngữ cảnh.

## 11. Bảo toàn nguyên nhân và tránh bắt lỗi quá rộng

Nên bắt những exception mà task có thể xử lý hoặc chuyển đổi có chủ đích:

~~~java
try {
    parseFile(file);
} catch (IOException ex) {
    throw new BuildException("Unable to read " + file, ex, getLocation());
} catch (SomeParserException ex) {
    throw new BuildException("Invalid document " + file, ex, getLocation());
}
~~~

Tránh:

~~~java
try {
    performTask();
} catch (Throwable ex) {
    throw new BuildException("Task failed");
}
~~~

`Throwable` bao gồm cả các lỗi nghiêm trọng của JVM như `OutOfMemoryError` hoặc `StackOverflowError`. Một custom task thông thường không nên bắt rồi chuyển mọi lỗi đó thành một BuildException chung chung. Việc bắt quá rộng còn làm mất thông tin loại lỗi và cause.

Nếu cần cleanup tài nguyên, dùng try-with-resources hoặc `finally`; không cần bắt `Throwable` chỉ để đóng stream. Nếu task phải chuyển đổi một exception runtime cụ thể, hãy bắt đúng loại và giữ cause.

## 12. Log an toàn và có thể đọc được trong CI

Log của build thường được lưu trong CI, chia sẻ cho nhiều người hoặc giữ lại lâu dài. Không nên ghi các giá trị bí mật như:

- Password, token, API key hoặc private key.
- Nội dung file credential.
- Header xác thực hoặc URL có chứa thông tin đăng nhập.
- Dữ liệu cá nhân không cần thiết cho chẩn đoán.

Thay vì in toàn bộ cấu hình, chỉ ghi tên file, số lượng mục, chế độ đã chọn hoặc tên property không nhạy cảm. Nếu lỗi liên quan credential, có thể báo `Authentication failed for repository 'internal-repo'. Check the configured credential entry.` mà không in credential.

Nên giữ log có cấu trúc và nhất quán:

~~~text
[INFO] Validating configuration: config/app.properties
[WARN] Optional metadata file not found; defaults will be used
[INFO] Configuration is valid for application 'Inventory Service'
~~~

Ant listener đã có cách trình bày riêng; không cần tự thêm prefix `[INFO]` nếu dự án không có quy ước đó. Ví dụ trên chỉ minh họa nội dung. Mỗi log message nên ngắn, có chủ thể và đủ ngữ cảnh.

## 13. Kiểm thử hành vi log và BuildException

Khi viết test cho custom task, nên kiểm tra các hành vi quan trọng:

- Attribute bắt buộc bị thiếu tạo BuildException.
- File không tồn tại tạo thông báo có tên file và location.
- Lỗi đọc file giữ cause.
- Input hợp lệ ghi thông báo thành công ở mức phù hợp.
- Warning tùy chọn không làm target thất bại.
- Fatal condition làm target thất bại và ngăn bước phụ thuộc tiếp tục.

Ant cung cấp cơ chế logging qua listener; trong test có thể gắn listener hoặc chạy một build test nhỏ để xác nhận message và mức log. Với lỗi, có thể kiểm tra exception type, message, location và cause thay vì chỉ so sánh toàn bộ chuỗi console, vốn dễ thay đổi theo phiên bản Ant hoặc listener.

Ví dụ kiểm tra thủ công:

~~~bash
ant validate
ant -verbose validate
ant -debug validate
~~~

Thử lần lượt với file hợp lệ, file không tồn tại và file thiếu key bắt buộc. Kết quả mong đợi:

| Trường hợp | Log/exception mong đợi | Build status |
|---|---|---|
| File hợp lệ | INFO xác nhận thành công | Thành công |
| Metadata tùy chọn thiếu | WARN nêu fallback | Thành công |
| File cấu hình bắt buộc thiếu | BuildException có file và location | Thất bại |
| File tồn tại nhưng không đọc được | BuildException giữ IOException làm cause | Thất bại |
| Property bắt buộc thiếu trong file | BuildException nêu tên property và file | Thất bại |

## 14. Những lỗi thường gặp khi ghi log và ném exception

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Log quá nhiều trong lần chạy bình thường | Chi tiết nội bộ được ghi ở INFO | Chuyển sang VERBOSE hoặc DEBUG |
| Người dùng không thấy thông tin khi chạy `-quiet` | Thông tin tiến độ được ghi ở mức thấp hơn ngưỡng | Chỉ giữ thông tin thật sự quan trọng ở mức phù hợp; không lạm dụng ERROR |
| Lỗi không chỉ ra dòng build file | `BuildException` không nhận `getLocation()` | Dùng constructor có `getLocation()` |
| Chỉ thấy message chung chung, không có nguyên nhân | Exception gốc bị bỏ | Truyền cause vào constructor `BuildException` |
| Cùng một lỗi xuất hiện hai lần | Task log ERROR rồi ném BuildException cùng nội dung | Với lỗi fatal, chỉ ném exception; log chi tiết bổ sung ở mức verbose/debug |
| Build tiếp tục sau khi thiếu cấu hình bắt buộc | Task chỉ ghi WARN hoặc nuốt exception | Ném `BuildException` và dừng target |
| Build thất bại vì file tùy chọn thiếu | Task coi mọi điều kiện thiếu là fatal | Định nghĩa fallback và dùng WARN nếu tiếp tục an toàn |
| Log chứa token hoặc mật khẩu | In toàn bộ cấu hình hoặc command line | Che hoặc bỏ dữ liệu nhạy cảm |
| Stack trace khó hiểu | Bắt `Throwable` hoặc tạo exception mới không giữ cause | Bắt exception cụ thể và giữ cause |
| Đường dẫn lỗi không đúng | Resolve đường dẫn không theo project basedir | Dùng `getProject().resolveFile(...)` cho đường dẫn tương đối |

## 15. Checklist thiết kế cho một custom task

Trước khi hoàn thiện custom task, hãy xác định:

1. Thông tin nào người chạy cần thấy ở mức INFO?
2. Điều kiện nào chỉ cần cảnh báo và có fallback?
3. Điều kiện nào phải làm build thất bại?
4. Message lỗi có chỉ ra file, property, target hoặc giá trị sai không?
5. Exception có gắn `getLocation()` không?
6. Exception gốc có được giữ làm cause không?
7. Task có tránh log trùng với BuildException không?
8. Có vô tình ghi credential hoặc dữ liệu nhạy cảm vào log không?
9. Chi tiết nội bộ có nằm ở VERBOSE/DEBUG thay vì INFO không?
10. Người dùng có biết bước tiếp theo để sửa lỗi không?

Một custom task tốt không cần tạo thật nhiều log. Nó cần ghi đúng thông tin ở đúng mức và báo lỗi theo cách Ant có thể xử lý nhất quán.

## Kết luận

Trong custom Ant Task, dùng `log(String)` cho thông tin INFO và `log(String, Project.MSG_...)` để chọn mức ERROR, WARN, INFO, VERBOSE hoặc DEBUG. Dùng `BuildException` khi task không thể hoàn thành; gắn `getLocation()` để Ant chỉ ra vị trí task trong build file và truyền exception gốc làm cause để giữ nguyên nguyên nhân kỹ thuật. Message nên nêu thao tác, tài nguyên, lý do thất bại và hướng xử lý. Với điều kiện tùy chọn có fallback, ghi WARN và tiếp tục có kiểm soát; với lỗi bắt buộc, ném exception thay vì chỉ log rồi chạy tiếp. Tránh `System.out`, bắt `Throwable`, log trùng lỗi và in bí mật vào CI output.

## Tài liệu tham khảo

- [Apache Ant – Writing Your Own Task](https://ant.apache.org/manual/develop.html)
- [Apache Ant API – Task](https://ant.apache.org/manual/api/org/apache/tools/ant/Task.html)
- [Apache Ant API – Project](https://ant.apache.org/manual/api/org/apache/tools/ant/Project.html)
- [Apache Ant API – BuildException](https://ant.apache.org/manual/api/org/apache/tools/ant/BuildException.html)
- [Apache Ant API – Location](https://ant.apache.org/manual/api/org/apache/tools/ant/Location.html)