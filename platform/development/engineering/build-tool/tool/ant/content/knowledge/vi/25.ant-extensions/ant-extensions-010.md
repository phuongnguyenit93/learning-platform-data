# Viết task chứa các task con bằng TaskContainer

Apache Ant cho phép một task tự định nghĩa nhận những task Ant khác làm phần tử con. Cơ chế này hữu ích khi muốn tạo một task bao quanh nhiều thao tác, chẳng hạn chạy một chuỗi bước theo thứ tự, thêm log trước và sau từng bước, áp dụng một chính sách chung hoặc điều phối các task theo một quy tắc riêng.

Để thực hiện điều đó, lớp task Java có thể triển khai interface **TaskContainer**. Ant sẽ gọi phương thức **addTask(Task task)** cho từng task con được khai báo trong XML. Task cha lưu các đối tượng này, sau đó quyết định cách thực thi chúng trong phương thức **execute()**.

Điểm quan trọng là TaskContainer chỉ cung cấp cơ chế nhận task con. Chính task do bạn viết quyết định thứ tự chạy, cách xử lý lỗi và những hành vi điều phối khác.

## 1. TaskContainer giải quyết vấn đề gì?

Một task thông thường nhận dữ liệu qua attribute hoặc nested element có cấu trúc. Ví dụ task copy nhận file, todir và một FileSet:

~~~xml
<copy file="config/default.properties"
      tofile="build/config/application.properties"/>
~~~

Những phần tử FileSet hoặc Path trong task Ant thường là cấu trúc dữ liệu được cấu hình theo quy tắc riêng. Chúng không phải là những task độc lập cần được thực thi tuần tự.

Một task container có mục đích khác: nó nhận các task như echo, mkdir, copy hoặc javac làm con và tự điều khiển chúng:

~~~xml
<task-group label="prepare">
    <echo message="Preparing output directory"/>
    <mkdir dir="build/output"/>
    <copy file="config/app.properties"
          tofile="build/output/app.properties"/>
</task-group>
~~~

Task **task-group** có thể:

- Ghi thông điệp trước khi bắt đầu.
- Thực thi từng task con theo thứ tự XML.
- Dừng khi một task con báo lỗi.
- Ghi thông điệp kết thúc nếu tất cả task con hoàn tất.
- Áp dụng chính sách chung như kiểm tra số lượng task hoặc ghi log thời gian.

Không cần tạo một task Java riêng cho từng thao tác con. Các task con vẫn là task Ant tiêu chuẩn hoặc task tùy chỉnh đã được đăng ký.

## 2. Interface TaskContainer

Interface **org.apache.tools.ant.TaskContainer** định nghĩa hợp đồng nhận task con thông qua một phương thức:

~~~java
void addTask(Task task);
~~~

Một lớp task thường mở rộng **org.apache.tools.ant.Task** và triển khai **TaskContainer**:

~~~java
package example;

import java.util.ArrayList;
import java.util.List;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;
import org.apache.tools.ant.TaskContainer;

public class TaskGroup extends Task implements TaskContainer {

    private final List<Task> nestedTasks = new ArrayList<Task>();

    public void addTask(Task task) {
        nestedTasks.add(task);
    }

    public void execute() throws BuildException {
        for (Task task : nestedTasks) {
            task.perform();
        }
    }
}
~~~

Các thành phần chính:

- **extends Task** giúp lớp trở thành một task Ant và cung cấp project context, logging, location cùng các tiện ích liên quan.
- **implements TaskContainer** cho Ant biết lớp có thể nhận task con.
- **addTask(Task task)** được Ant gọi khi cấu hình từng task con.
- **nestedTasks** lưu các task theo thứ tự chúng được khai báo.
- **execute()** điều khiển việc chạy các task đã nhận.

Danh sách là một **ArrayList**, nên giữ thứ tự thêm vào. Trong ví dụ, task con đầu tiên trong XML được thực thi trước task con thứ hai.

## 3. Ant chuyển XML thành các task con như thế nào?

Khi Ant đọc một lời gọi task container, nó tạo và cấu hình task cha, sau đó xử lý những phần tử task được lồng bên trong.

Ví dụ:

~~~xml
<task-group label="prepare">
    <echo message="Step one"/>
    <mkdir dir="build/output"/>
</task-group>
~~~

Quá trình khái quát:

1. Ant nhận diện phần tử task-group thông qua tên task đã đăng ký.
2. Ant tạo instance của lớp TaskGroup.
3. Attribute label được ánh xạ tới setter tương ứng nếu lớp có khai báo setter.
4. Ant tạo và cấu hình task echo.
5. Ant gọi addTask() của TaskGroup để chuyển task echo vào container.
6. Ant tạo và cấu hình task mkdir rồi gọi addTask() lần nữa.
7. Khi đến lượt thực thi task-group, Ant gọi execute() của task cha.
8. Task cha duyệt danh sách và thực thi từng task con.

Có thể hình dung:

~~~text
XML build file
    |
    v
<task-group>
    |-- <echo/>
    |-- <mkdir/>
    |-- <copy/>
    |
    v
Ant cấu hình các task con
    |
    +---- addTask(echo)
    +---- addTask(mkdir)
    +---- addTask(copy)
    |
    v
TaskGroup.execute()
    |
    +---- echo.perform()
    +---- mkdir.perform()
    +---- copy.perform()
~~~

Ant đã tạo và cấu hình task con trước khi task container thực thi. Vì vậy, addTask() nên tập trung lưu task vào danh sách. Không nên thực thi task ngay trong addTask(), bởi khi đó container mất quyền điều khiển trình tự tổng thể và có thể chạy task trước khi toàn bộ cấu hình của cha được hoàn tất.

## 4. Đăng ký custom task bằng taskdef

Sau khi biên dịch lớp Java thành class file hoặc đóng gói thành JAR, cần đăng ký tên task để build file có thể sử dụng.

Ví dụ đăng ký một lớp nằm trong JAR:

~~~xml
<taskdef name="task-group"
         classname="example.TaskGroup"
         classpath="lib/ant-custom-tasks.jar"/>
~~~

Sau đó gọi task trong target:

~~~xml
<target name="demo">
    <task-group>
        <echo message="First child task"/>
        <mkdir dir="build/output"/>
    </task-group>
</target>
~~~

Trong đó:

- **name** là tên XML mà build file sử dụng.
- **classname** là tên đầy đủ của lớp Java, gồm package.
- **classpath** chỉ tới JAR hoặc thư mục chứa class của task tùy chỉnh.

Nếu task được đóng gói trong một thư mục class thay vì JAR, classpath có thể trỏ trực tiếp tới thư mục đó:

~~~xml
<taskdef name="task-group"
         classname="example.TaskGroup"
         classpath="build/ant-tasks"/>
~~~

Task tùy chỉnh cần được biên dịch với Ant API trên classpath. Khi chạy, Ant phải có thể nạp lớp task và các dependency mà lớp đó cần.

### Ví dụ biên dịch task tùy chỉnh

Giả sử mã nguồn nằm trong **src/ant-tasks**:

~~~xml
<property name="ant.lib" location="lib/ant"/>
<property name="task.classes" location="build/ant-tasks"/>

<target name="compile-ant-tasks">
    <mkdir dir="${task.classes}"/>

    <javac srcdir="src/ant-tasks"
           destdir="${task.classes}"
           includeantruntime="false">
        <classpath>
            <pathelement location="${ant.lib}/ant.jar"/>
        </classpath>
    </javac>
</target>
~~~

Trong dự án thực tế, đường dẫn tới **ant.jar** phụ thuộc vào cách cài đặt Ant. Có thể lấy JAR từ thư mục lib của Ant hoặc cấu hình một thư mục thư viện riêng cho việc phát triển custom task.

Một cách triển khai đơn giản hơn là biên dịch và đóng gói custom task trước, sau đó đăng ký bằng taskdef ở cấp project. Khi taskdef được thực thi, classpath phải trỏ tới nơi chứa class đã biên dịch.

## 5. Kết hợp attribute với TaskContainer

Task container không chỉ nhận task con. Nó vẫn có thể nhận attribute thông thường thông qua các setter public.

Ví dụ mở rộng TaskGroup với attribute label:

~~~java
package example;

import java.util.ArrayList;
import java.util.List;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;
import org.apache.tools.ant.TaskContainer;

public class TaskGroup extends Task implements TaskContainer {

    private final List<Task> nestedTasks = new ArrayList<Task>();
    private String label = "unnamed";

    public void setLabel(String label) {
        this.label = label;
    }

    public void addTask(Task task) {
        nestedTasks.add(task);
    }

    public void execute() throws BuildException {
        log("Starting task group: " + label);

        for (Task task : nestedTasks) {
            task.perform();
        }

        log("Finished task group: " + label);
    }
}
~~~

Cách sử dụng:

~~~xml
<taskdef name="task-group"
         classname="example.TaskGroup"
         classpath="lib/ant-custom-tasks.jar"/>

<target name="demo">
    <task-group label="prepare-catalog">
        <echo message="Create catalog output"/>
        <mkdir dir="build/catalog"/>
    </task-group>

    <task-group label="prepare-billing">
        <echo message="Create billing output"/>
        <mkdir dir="build/billing"/>
    </task-group>
</target>
~~~

Ant ánh xạ attribute **label** tới phương thức **setLabel(String label)** theo quy tắc introspection của JavaBean. Tên attribute được chuyển thành tên setter tương ứng.

Có thể bổ sung các attribute khác như failOnError, description hoặc mode. Tuy nhiên, nên giữ giao diện nhỏ và chỉ thêm những giá trị thực sự làm thay đổi hành vi của container.

## 6. Vì sao nên gọi perform() thay vì execute()?

Khi chạy một task con, nên gọi:

~~~java
task.perform();
~~~

thay vì gọi trực tiếp:

~~~java
task.execute();
~~~

Phương thức **perform()** là điểm thực thi task theo lifecycle của Ant. Nó xử lý ngữ cảnh thực thi và các cơ chế xung quanh task như logging, thông báo bắt đầu/kết thúc và xử lý lỗi theo cách Ant quản lý.

Gọi trực tiếp execute() bỏ qua một phần lifecycle đó. Một số task có thể vẫn chạy, nhưng container không nên tự bỏ qua cơ chế thực thi chuẩn của Ant.

Do đó, mẫu thông dụng là:

~~~java
for (Task task : nestedTasks) {
    task.perform();
}
~~~

Không cần tự tạo instance task con bằng constructor, cũng không cần tự gán Project hoặc Location cho từng task. Ant đã tạo và cấu hình các task con trong quá trình xử lý XML trước khi chuyển chúng cho TaskContainer.

## 7. Thứ tự thực thi và xử lý lỗi

TaskContainer không tự áp đặt chính sách tuần tự hay song song. Chính phần execute() của custom task quyết định điều đó.

Với một container tuần tự, nên duyệt danh sách theo thứ tự thêm vào:

~~~java
public void execute() throws BuildException {
    for (Task task : nestedTasks) {
        task.perform();
    }
}
~~~

Nếu task con thứ hai thất bại và ném **BuildException**, ngoại lệ sẽ truyền ra khỏi execute(). Vòng lặp dừng tại đó, các task con phía sau không được chạy và Ant đánh dấu build thất bại.

Ví dụ XML:

~~~xml
<task-group>
    <echo message="This task runs"/>
    <fail message="Stop the task group"/>
    <echo message="This task is skipped"/>
</task-group>
~~~

Khi chạy container theo mẫu tuần tự mặc định, task fail làm dừng chuỗi. Thông điệp cuối không được in.

Đây thường là hành vi phù hợp cho các bước build phụ thuộc lẫn nhau: nếu tạo thư mục thất bại thì không nên tiếp tục copy; nếu biên dịch thất bại thì không nên đóng gói.

### Có nên bắt BuildException không?

Nếu muốn container tiếp tục chạy những task còn lại dù một task con thất bại, có thể bắt ngoại lệ và ghi nhận lỗi. Tuy nhiên, không nên nuốt lỗi rồi trả về thành công.

Ví dụ một chính sách thu thập lỗi:

~~~java
public void execute() throws BuildException {
    BuildException firstFailure = null;

    for (Task task : nestedTasks) {
        try {
            task.perform();
        } catch (BuildException ex) {
            if (firstFailure == null) {
                firstFailure = ex;
            }
            log("Nested task failed: " + ex.getMessage());
        }
    }

    if (firstFailure != null) {
        throw firstFailure;
    }
}
~~~

Với cách này, các task sau vẫn được thử chạy, nhưng container cuối cùng vẫn báo lỗi cho Ant. Chính sách này chỉ phù hợp khi các task độc lập và việc tiếp tục có ý nghĩa, chẳng hạn thu thập nhiều kết quả kiểm tra. Không dùng cho chuỗi thao tác mà bước sau cần đầu ra hợp lệ của bước trước.

Nếu cần cleanup khi lỗi, có thể dùng try/finally:

~~~java
public void execute() throws BuildException {
    try {
        for (Task task : nestedTasks) {
            task.perform();
        }
    } finally {
        log("Task group execution finished");
    }
}
~~~

Khối finally được thực hiện khi task con ném BuildException. Tuy nhiên, cleanup thực tế cần được thiết kế cẩn thận: nếu cleanup cũng ném lỗi, nó có thể che mất lỗi ban đầu. Với tác vụ có tài nguyên ngoài JVM như server hoặc container, nên cân nhắc task cleanup riêng hoặc cơ chế xử lý lỗi rõ ràng.

## 8. Kiểm tra đầu vào của container

Một custom task có thể xác thực số lượng task con hoặc attribute trước khi thực thi.

Ví dụ bắt buộc có ít nhất một task con:

~~~java
public void execute() throws BuildException {
    if (nestedTasks.isEmpty()) {
        throw new BuildException(
            "task-group requires at least one nested task",
            getLocation()
        );
    }

    for (Task task : nestedTasks) {
        task.perform();
    }
}
~~~

Dùng **getLocation()** khi tạo BuildException giúp Ant gắn lỗi với vị trí task trong build file. Điều này hữu ích khi một project có nhiều lần gọi cùng một custom task.

Có thể kiểm tra attribute trước khi chạy:

~~~java
public void execute() throws BuildException {
    if (label == null || label.trim().isEmpty()) {
        throw new BuildException(
            "Attribute label must not be empty",
            getLocation()
        );
    }

    for (Task task : nestedTasks) {
        task.perform();
    }
}
~~~

Nếu một giá trị là bắt buộc, cũng có thể kiểm tra nó ngay trong setter hoặc trong execute(). Kiểm tra trong execute() thường giúp gom validation về một chỗ và bảo đảm thông báo lỗi nhất quán.

## 9. TaskContainer khác với nested element thông thường

Không phải mọi phần tử con trong XML Ant đều là task. Có hai nhóm cần phân biệt:

1. **Nested task** là một task có thể thực thi, ví dụ echo, mkdir, copy hoặc javac.
2. **Nested data element** là cấu trúc dữ liệu được task cha cấu hình, ví dụ fileset, path hoặc mapper.

TaskContainer được thiết kế để nhận nhóm thứ nhất thông qua addTask(Task task). Nếu custom task cần nhận một data element có cấu trúc, nên dùng các quy tắc nested element của Ant như **createX()**, **addX()** hoặc **addConfiguredX()**.

Ví dụ một task nhận FileSet có thể khai báo:

~~~java
private FileSet sourceSet;

public void addFileset(FileSet fileset) {
    this.sourceSet = fileset;
}
~~~

XML tương ứng:

~~~xml
<my-copy-task>
    <fileset dir="src">
        <include name="**/*.properties"/>
    </fileset>
</my-copy-task>
~~~

FileSet không phải task được thực thi độc lập bằng perform(). Nó là cấu hình mô tả tập resource cho task cha.

Ngược lại:

~~~xml
<task-group>
    <copy file="src/a.txt" tofile="build/a.txt"/>
    <echo message="Copy completed"/>
</task-group>
~~~

Copy và echo là task con, vì vậy phù hợp với TaskContainer.

Không nên triển khai TaskContainer chỉ để nhận FileSet, Path hoặc một cấu trúc dữ liệu khác. Hãy chọn cơ chế nested element phù hợp với loại nội dung XML mà task cần nhận.

## 10. Khi nào dùng TaskContainer, khi nào dùng macro hoặc sequential?

Ant đã có task **sequential** để chạy một chuỗi task theo thứ tự. Trước khi viết custom TaskContainer, cần xác định có thực sự cần logic Java riêng hay không.

| Cơ chế | Mục đích | Khi nên dùng |
|---|---|---|
| **sequential** | Chạy một nhóm task lần lượt | Chỉ cần nhóm task theo thứ tự |
| **macrodef** | Tái sử dụng một mẫu task với attribute/element đầu vào | Cần cùng một chuỗi task ở nhiều nơi |
| **TaskContainer** | Viết task Java nhận và điều phối các task con | Cần logic điều phối riêng, validation hoặc tích hợp Java |
| **target** | Tổ chức các bước build theo dependency graph | Cần gọi theo tên target, phụ thuộc target hoặc điều khiển luồng build |

Ví dụ dùng sequential nếu chỉ cần chạy tuần tự:

~~~xml
<sequential>
    <echo message="Prepare"/>
    <mkdir dir="build/output"/>
    <copy file="config/app.properties"
          tofile="build/output/app.properties"/>
</sequential>
~~~

Dùng macrodef nếu cùng chuỗi đó cần chạy cho nhiều module với đầu vào khác nhau:

~~~xml
<macrodef name="prepare-module">
    <attribute name="name"/>
    <sequential>
        <echo message="Prepare @{name}"/>
        <mkdir dir="build/@{name}"/>
    </sequential>
</macrodef>
~~~

Dùng TaskContainer khi cần viết Java để điều phối task con theo một chính sách mà các cơ chế khai báo sẵn không thể thể hiện rõ, chẳng hạn xác thực số task, ghi log theo ngữ cảnh Java hoặc thu thập lỗi theo quy tắc riêng.

## 11. Ví dụ hoàn chỉnh: custom task bao quanh các bước chuẩn bị

Giả sử cần một task **task-group** để:

- Nhận attribute label.
- Nhận nhiều task con.
- Ghi log bắt đầu và kết thúc.
- Yêu cầu có ít nhất một task con.
- Dừng ngay khi một task con thất bại.

Lớp Java:

~~~java
package example;

import java.util.ArrayList;
import java.util.List;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;
import org.apache.tools.ant.TaskContainer;

public class TaskGroup extends Task implements TaskContainer {

    private final List<Task> nestedTasks = new ArrayList<Task>();
    private String label;

    public void setLabel(String label) {
        this.label = label;
    }

    public void addTask(Task task) {
        if (task == null) {
            throw new BuildException(
                "Nested task must not be null",
                getLocation()
            );
        }
        nestedTasks.add(task);
    }

    @Override
    public void execute() throws BuildException {
        if (label == null || label.trim().isEmpty()) {
            throw new BuildException(
                "Attribute label is required",
                getLocation()
            );
        }

        if (nestedTasks.isEmpty()) {
            throw new BuildException(
                "At least one nested task is required",
                getLocation()
            );
        }

        log("Starting group: " + label);

        for (Task task : nestedTasks) {
            task.perform();
        }

        log("Completed group: " + label);
    }
}
~~~

Đăng ký task:

~~~xml
<taskdef name="task-group"
         classname="example.TaskGroup"
         classpath="lib/ant-custom-tasks.jar"/>
~~~

Sử dụng trong build file:

~~~xml
<target name="prepare-catalog">
    <task-group label="catalog">
        <echo message="Create catalog directories"/>
        <mkdir dir="build/catalog/classes"/>
        <mkdir dir="build/catalog/resources"/>
        <copy file="modules/catalog/config/app.properties"
              tofile="build/catalog/resources/app.properties"/>
    </task-group>
</target>

<target name="prepare-billing">
    <task-group label="billing">
        <echo message="Create billing directories"/>
        <mkdir dir="build/billing/classes"/>
        <mkdir dir="build/billing/resources"/>
        <copy file="modules/billing/config/app.properties"
              tofile="build/billing/resources/app.properties"/>
    </task-group>
</target>
~~~

Mỗi lần gọi task-group có một instance riêng và một danh sách task con riêng. Container thực thi các task theo thứ tự XML. Nếu copy thất bại, BuildException truyền ra ngoài và các bước phía sau trong cùng nhóm không được chạy.

## 12. Lưu ý về trạng thái và khả năng tái sử dụng

Task container nên giữ trạng thái ở mức tối thiểu. Danh sách task con là dữ liệu của một instance task, vì vậy không nên dùng biến static để lưu danh sách.

Ví dụ không nên dùng:

~~~java
private static final List<Task> nestedTasks =
    new ArrayList<Task>();
~~~

Một danh sách static có thể làm task con từ các lần gọi khác nhau bị trộn lẫn hoặc tạo ra trạng thái dùng chung ngoài ý muốn.

Nên dùng trường instance:

~~~java
private final List<Task> nestedTasks =
    new ArrayList<Task>();
~~~

Ngoài ra:

- Không lưu task con vào property toàn project.
- Không thực thi task trong addTask().
- Không gọi execute() trực tiếp trên task con.
- Không chạy cùng một task con nhiều lần trừ khi đó là hành vi được thiết kế rõ ràng.
- Không giữ tham chiếu task sau khi container hoàn thành nếu không có nhu cầu cụ thể.
- Không bắt và bỏ qua BuildException nếu kết quả thất bại phải được phản ánh về Ant.

TaskContainer nên có một trách nhiệm rõ ràng: nhận task con và áp dụng một chính sách thực thi nhất quán.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo task tùy chỉnh không tồn tại | Chưa đăng ký taskdef hoặc classpath sai | Kiểm tra name, classname và classpath |
| Ant báo task con không hợp lệ | Phần tử con không phải task đã đăng ký hoặc không được hỗ trợ | Dùng task Ant hợp lệ hoặc đăng ký custom task trước |
| Không có task con nào chạy | addTask() không lưu task hoặc execute() không duyệt danh sách | Lưu trong addTask và thực thi trong execute |
| Task con chạy ngay khi đọc XML | addTask() gọi perform() quá sớm | Chỉ lưu task trong addTask; thực thi trong execute |
| Task con không có log/lifecycle như mong đợi | Gọi execute() trực tiếp | Gọi perform() |
| Task con chạy sai thứ tự | Dùng collection không giữ thứ tự hoặc sắp xếp lại danh sách | Dùng List có thứ tự thêm và duyệt tuần tự |
| Build vẫn thành công sau task con thất bại | Bắt BuildException nhưng không ném lại | Truyền lỗi ra ngoài hoặc tổng hợp rồi ném BuildException |
| FileSet không được nhận như task con | FileSet là nested data element, không phải task | Dùng addFileset/createFileset hoặc cơ chế nested element |
| Nhiều lần gọi bị trộn task | Dùng static collection hoặc trạng thái dùng chung | Dùng collection instance riêng cho mỗi task |
| Thông báo lỗi thiếu vị trí XML | Tạo BuildException không gắn location | Dùng constructor nhận getLocation() |

## 14. Nguyên tắc triển khai

- Triển khai **TaskContainer** khi task Java cần nhận các task Ant khác làm con.
- Dùng **addTask(Task task)** để lưu từng task được Ant cấu hình.
- Dùng List giữ thứ tự khai báo nếu container chạy tuần tự.
- Đợi đến **execute()** mới điều phối task con.
- Gọi **perform()** để thực thi task con theo lifecycle của Ant.
- Để BuildException truyền ra ngoài nếu task con thất bại và build cần dừng.
- Chỉ tiếp tục sau lỗi khi các task con độc lập và chính sách lỗi được xác định rõ.
- Dùng setter public cho attribute và taskdef để đăng ký lớp custom task.
- Dùng create/add/addConfigured cho nested data element; TaskContainer dành cho nested task.
- Tránh static state và giữ danh sách task riêng cho từng instance.
- Chọn sequential hoặc macrodef nếu chỉ cần gom nhóm hay tái sử dụng task mà không cần logic Java riêng.

TaskContainer biến một task Ant tùy chỉnh thành nơi tiếp nhận và điều phối các task con. Ant lo việc tạo và cấu hình từng task; custom task lưu chúng qua addTask() rồi quyết định cách thực thi trong execute(). Khi giữ đúng ranh giới này, task container có thể bổ sung validation, logging, thứ tự và chính sách xử lý lỗi mà vẫn tận dụng được các task Ant sẵn có.

## Tài liệu tham khảo

- [Apache Ant — Writing Tasks](https://ant.apache.org/manual/develop.html)
- [Apache Ant API — TaskContainer](https://ant.apache.org/manual/api/org/apache/tools/ant/TaskContainer.html)
- [Apache Ant API — Task](https://ant.apache.org/manual/api/org/apache/tools/ant/Task.html)
- [Apache Ant — TaskDef Task](https://ant.apache.org/manual/Tasks/taskdef.html)

