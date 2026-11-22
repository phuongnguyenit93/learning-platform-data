# Nhận nội dung lồng bằng addText và phần tử lồng bằng create, add, addConfigured

Khi viết một custom task cho Apache Ant, build file có thể truyền dữ liệu vào task qua thuộc tính XML, phần văn bản nằm giữa thẻ mở và thẻ đóng, hoặc các phần tử XML lồng bên trong task. Ant dùng cơ chế introspection để tìm các phương thức Java phù hợp và chuyển cấu trúc XML thành lời gọi phương thức trên đối tượng task.

Ví dụ, một task có thể nhận nội dung văn bản trực tiếp:

~~~xml
<greeting>Build completed successfully.</greeting>
~~~

Một task khác có thể nhận nhiều phần tử con với thuộc tính riêng:

~~~xml
<report>
    <item name="summary" path="reports/summary.xml" />
    <item name="detail" path="reports/detail.xml" />
</report>
~~~

Để hỗ trợ các dạng XML này, custom task thường triển khai:

- `addText(String)` để nhận văn bản trực tiếp trong phần thân phần tử.
- `createX()` để tự tạo đối tượng cho phần tử lồng tên `x`.
- `addX(X)` để nhận một đối tượng phần tử lồng do Ant tạo.
- `addConfiguredX(X)` để nhận đối tượng sau khi Ant đã cấu hình xong các thuộc tính và phần tử con của nó.

Hiểu thời điểm các phương thức được gọi rất quan trọng. Nếu task cần kiểm tra thuộc tính của phần tử con, phương thức `addConfiguredX` thường phù hợp hơn `addX`. Nếu task muốn tự quản lý cách tạo đối tượng, `createX` cho phép nó tạo và lưu đối tượng trước khi Ant cấu hình phần tử đó.

## 1. Ant ánh xạ XML sang phương thức Java như thế nào?

Một custom task thường kế thừa `org.apache.tools.ant.Task`. Khi Ant đọc build file, nó tạo đối tượng task, gán các thuộc tính XML thông qua setter và xử lý nội dung lồng bằng các phương thức mà task cung cấp.

Ví dụ:

~~~xml
<greeting message="Hello Ant" />
~~~

Nếu task có phương thức:

~~~java
public void setMessage(String message) {
    this.message = message;
}
~~~

Ant gọi `setMessage("Hello Ant")` để gán thuộc tính XML `message`.

Với phần tử lồng:

~~~xml
<report>
    <item name="summary" path="reports/summary.xml" />
</report>
~~~

Tên phần tử `item` được ánh xạ tới một trong các phương thức tương ứng trên lớp task:

- `createItem()`
- `addItem(Item item)`
- `addConfiguredItem(Item item)`

Kiểu Java `Item` mô tả đối tượng nhận các thuộc tính hoặc phần tử con của XML `item`. Những thuộc tính như `name` và `path` thường được ánh xạ tới `setName(String)` và `setPath(String)` trên lớp đó.

Ant không yêu cầu mọi task phải hỗ trợ cả ba kiểu tiếp nhận phần tử lồng. Chọn cách phù hợp với vòng đời và cách task cần xử lý dữ liệu.

## 2. Nhận văn bản trực tiếp bằng addText

### 2.1. addText nhận nội dung giữa thẻ mở và thẻ đóng

Nếu build file có văn bản trực tiếp bên trong phần tử task, Ant có thể chuyển nội dung đó vào phương thức public `addText(String)`.

Ví dụ build file:

~~~xml
<greeting>Build completed successfully.</greeting>
~~~

Lớp task:

~~~java
package com.example.ant;

import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class GreetingTask extends Task {

    private final StringBuilder text = new StringBuilder();

    public void addText(String value) {
        text.append(value);
    }

    @Override
    public void execute() throws BuildException {
        String message = text.toString().trim();

        if (message.isEmpty()) {
            throw new BuildException("Greeting text must not be empty");
        }

        log(message);
    }
}
~~~

Khi Ant xử lý phần tử `greeting`, nội dung văn bản được chuyển vào `addText`. Task giữ nội dung trong `StringBuilder`, sau đó sử dụng nó trong `execute()`.

Dùng `StringBuilder` giúp xử lý an toàn khi văn bản được cung cấp thành nhiều đoạn. Nếu nội dung chỉ là một chuỗi đơn giản, vẫn có thể lưu trực tiếp vào một trường String, nhưng cần quyết định rõ cách xử lý khi phương thức được gọi nhiều lần.

### 2.2. Khoảng trắng và xuống dòng

XML thường có khoảng trắng do cách trình bày build file:

~~~xml
<greeting>
    Build completed successfully.
</greeting>
~~~

Nội dung nhận được có thể bao gồm ký tự xuống dòng và khoảng trắng thụt lề. Nếu task chỉ cần một thông điệp, gọi `trim()` trước khi sử dụng thường hợp lý.

Nếu khoảng trắng có ý nghĩa, ví dụ task nhận nội dung mẫu hoặc đoạn văn cần giữ nguyên định dạng, không được tự động trim hay chuẩn hóa. Hãy lưu nội dung nguyên trạng và để chính sách xử lý thuộc về yêu cầu của task.

Không nên dùng `addText` để nhận dữ liệu có cấu trúc phức tạp như nhiều mục, mỗi mục có thuộc tính riêng. Với trường hợp đó, phần tử XML lồng và các phương thức `create`, `add` hoặc `addConfigured` dễ biểu đạt và xác thực hơn.

### 2.3. Văn bản của phần tử con thuộc về phần tử con

Giả sử build file:

~~~xml
<report>
    <description>Monthly billing report</description>
</report>
~~~

Văn bản `Monthly billing report` thuộc phần tử `description`. Nếu `description` là một kiểu phần tử lồng riêng, lớp đại diện cho phần tử đó cần hỗ trợ nhận text, ví dụ bằng phương thức `addText(String)` của chính lớp đó.

Phương thức `addText` của task cha nhận văn bản trực tiếp trong phần thân của task cha. Nó không tự động nhận nội dung nằm bên trong mọi phần tử con.

### 2.4. Khi nào dùng addText?

Dùng `addText` khi nội dung là một khối văn bản đơn giản, chẳng hạn:

- Thông điệp cần in hoặc ghi log.
- Một biểu thức hoặc đoạn script mà task xử lý như văn bản.
- Một mẫu nội dung ngắn.
- Một đoạn cấu hình dạng text mà định dạng của task quy định.

Nếu cần nhiều thuộc tính có tên, nhiều phần tử con hoặc cấu trúc lặp lại, hãy dùng nested element thay vì nhồi toàn bộ dữ liệu vào một chuỗi.

## 3. Nhận phần tử lồng bằng createX

### 3.1. createX để task tự tạo đối tượng

Nếu XML có phần tử con tên `item`, Ant có thể gọi phương thức `createItem()` trên lớp task. Phương thức này không nhận tham số và trả về đối tượng đại diện cho phần tử lồng.

Ví dụ:

~~~java
package com.example.ant;

import java.util.ArrayList;
import java.util.List;
import org.apache.tools.ant.BuildException;
import org.apache.tools.ant.Task;

public class ReportTask extends Task {

    private final List<ItemSpec> items = new ArrayList<ItemSpec>();

    public ItemSpec createItem() {
        ItemSpec item = new ItemSpec();
        items.add(item);
        return item;
    }

    @Override
    public void execute() throws BuildException {
        if (items.isEmpty()) {
            throw new BuildException("At least one item is required");
        }

        for (ItemSpec item : items) {
            if (item.getName() == null || item.getName().trim().isEmpty()) {
                throw new BuildException("Each item needs a name");
            }

            log("Report item: " + item.getName()
                + ", path=" + item.getPath());
        }
    }

    public static class ItemSpec {
        private String name;
        private String path;

        public void setName(String name) {
            this.name = name;
        }

        public void setPath(String path) {
            this.path = path;
        }

        public String getName() {
            return name;
        }

        public String getPath() {
            return path;
        }
    }
}
~~~

Build file:

~~~xml
<report>
    <item name="summary" path="reports/summary.xml" />
    <item name="detail" path="reports/detail.xml" />
</report>
~~~

Khi gặp mỗi phần tử `item`, Ant gọi `createItem()`, nhận đối tượng `ItemSpec`, rồi cấu hình các thuộc tính của phần tử đó thông qua setter. Task đã thêm đối tượng vào danh sách nên có thể xử lý tất cả item trong `execute()`.

### 3.2. createX được gọi trước khi đối tượng được cấu hình

Phương thức `createItem()` tạo và trả về đối tượng. Sau đó Ant mới gán các thuộc tính XML như `name` và `path`, hoặc cấu hình các phần tử con của item.

Vì vậy, không kiểm tra giá trị `name` hoặc `path` ngay trong `createItem()`: lúc đó chúng chưa được gán. Hãy kiểm tra trong `execute()`, hoặc tổ chức xử lý ở thời điểm sau khi cấu hình hoàn tất.

### 3.3. Quy tắc đặt tên

Tên phần tử XML được chuyển thành tên phương thức theo quy ước JavaBeans của Ant. Ví dụ:

| Phần tử XML | Phương thức create |
|---|---|
| `<item>` | `createItem()` |
| `<source>` | `createSource()` |
| `<classpath-entry>` | Dùng quy tắc tên phần tử và introspection tương ứng; nên ưu tiên tên XML đơn giản, rõ ràng |

Phương thức create phải public, không có tham số và trả về kiểu đối tượng mà Ant có thể cấu hình. Kiểu trả về thường là một bean có setter công khai hoặc một Ant data type phù hợp.

## 4. Nhận phần tử lồng bằng addX

### 4.1. addX nhận đối tượng do Ant tạo

Một cách khác là cung cấp phương thức `addItem(ItemSpec item)`. Ant tạo đối tượng phần tử lồng và chuyển nó cho phương thức add của task:

~~~java
public class ReportTask extends Task {

    private final List<ItemSpec> items = new ArrayList<ItemSpec>();

    public void addItem(ItemSpec item) {
        items.add(item);
    }

    @Override
    public void execute() throws BuildException {
        for (ItemSpec item : items) {
            // Xử lý các item sau khi cấu hình đã hoàn tất.
        }
    }
}
~~~

Lớp `ItemSpec` vẫn có thể là bean với các setter:

~~~java
public class ItemSpec {
    private String name;
    private String path;

    public void setName(String name) {
        this.name = name;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public String getName() {
        return name;
    }

    public String getPath() {
        return path;
    }
}
~~~

Build file sử dụng cùng cấu trúc:

~~~xml
<report>
    <item name="summary" path="reports/summary.xml" />
    <item name="detail" path="reports/detail.xml" />
</report>
~~~

Khác với `createItem()`, task không tự khởi tạo item trong phương thức create. Ant tạo đối tượng phù hợp rồi gọi `addItem` để chuyển đối tượng đó vào task.

### 4.2. addX được gọi trước khi phần tử con cấu hình xong

Phương thức `addItem(ItemSpec item)` được gọi trước khi Ant hoàn tất việc gán các thuộc tính và cấu hình lồng cho đối tượng item. Vì vậy, phương thức này nên chỉ tiếp nhận và lưu đối tượng, không nên đọc các giá trị cấu hình để quyết định nghiệp vụ ngay tại thời điểm đó.

Ví dụ không nên làm:

~~~java
public void addItem(ItemSpec item) {
    if (item.getName() == null) {
        throw new BuildException("Missing item name");
    }

    items.add(item);
}
~~~

Tại thời điểm `addItem` được gọi, `setName` có thể chưa được thực hiện. Kiểm tra trong `execute()` sẽ an toàn hơn:

~~~java
public void addItem(ItemSpec item) {
    items.add(item);
}

@Override
public void execute() throws BuildException {
    for (ItemSpec item : items) {
        if (item.getName() == null || item.getName().trim().isEmpty()) {
            throw new BuildException("Each item needs a name");
        }
    }
}
~~~

### 4.3. Khi nào dùng addX?

Dùng `addX` khi task chỉ cần tiếp nhận đối tượng và có thể xử lý nó sau khi toàn bộ cấu hình đã được Ant hoàn tất, thường là trong `execute()`.

Nếu task cần xác thực ngay sau khi phần tử lồng được cấu hình, `addConfiguredX` thể hiện thời điểm đó rõ hơn.

## 5. Nhận phần tử lồng bằng addConfiguredX

### 5.1. addConfiguredX được gọi sau khi cấu hình hoàn tất

Phương thức `addConfiguredItem(ItemSpec item)` nhận đối tượng sau khi Ant đã cấu hình các thuộc tính và phần tử con của nó.

Ví dụ:

~~~java
public class ReportTask extends Task {

    private final List<ItemSpec> items = new ArrayList<ItemSpec>();

    public void addConfiguredItem(ItemSpec item) {
        if (item.getName() == null || item.getName().trim().isEmpty()) {
            throw new BuildException("Item name is required");
        }

        if (item.getPath() == null || item.getPath().trim().isEmpty()) {
            throw new BuildException("Item path is required");
        }

        items.add(item);
    }

    @Override
    public void execute() throws BuildException {
        for (ItemSpec item : items) {
            log("Processing " + item.getName()
                + " from " + item.getPath());
        }
    }
}
~~~

Ant thực hiện theo trình tự:

1. Tạo đối tượng `ItemSpec`.
2. Gán thuộc tính XML qua setter.
3. Cấu hình các phần tử con của item nếu có.
4. Gọi `addConfiguredItem(item)`.
5. Task lưu đối tượng đã được xác thực để xử lý sau.

Vì đối tượng đã được cấu hình, task có thể kiểm tra `name`, `path` hoặc trạng thái nội bộ ngay trong phương thức này.

### 5.2. Ví dụ XML

~~~xml
<report>
    <item name="summary" path="reports/summary.xml" />
    <item name="detail" path="reports/detail.xml" />
</report>
~~~

Cùng một XML có thể được xử lý bởi `createItem`, `addItem` hoặc `addConfiguredItem`, tùy phương thức mà lớp task cung cấp. Cách triển khai quyết định vòng đời nhận đối tượng.

### 5.3. Kiểm tra phần tử lồng tại đúng thời điểm

Nếu một item có cấu trúc lồng:

~~~xml
<report>
    <item name="summary" path="reports/summary.xml">
        <option key="includeTotals" value="true" />
    </item>
</report>
~~~

Ant phải cấu hình cả thuộc tính của item và phần tử option trước khi gọi `addConfiguredItem`. Vì vậy, đây là nơi thích hợp để xác thực rằng option bắt buộc đã được cung cấp hoặc các giá trị có quan hệ với nhau là hợp lệ.

Không nên thực hiện công việc nặng hoặc có side effect trong `addConfiguredItem`, chẳng hạn tạo archive hoặc ghi dữ liệu ra hệ thống bên ngoài. Phương thức này nên tập trung vào việc kiểm tra và tiếp nhận cấu hình; công việc chính nên được thực hiện trong `execute()`.

## 6. So sánh create, add và addConfigured

| Cơ chế | Ai tạo đối tượng? | Khi nào task nhận đối tượng? | Có thể đọc cấu hình hoàn chỉnh ngay lúc nhận? |
|---|---|---|---|
| `createX()` | Task tạo và trả về đối tượng | Ant gọi create trước khi cấu hình phần tử | Không; Ant cấu hình đối tượng sau khi create trả về |
| `addX(X)` | Ant tạo đối tượng phù hợp | add được gọi trước khi cấu hình phần tử hoàn tất | Không nên; lưu lại rồi xử lý sau |
| `addConfiguredX(X)` | Ant tạo đối tượng phù hợp | Sau khi Ant cấu hình phần tử xong | Có; thích hợp để validate cấu hình |

Một số hướng dẫn thực hành:

- Chọn `createX` khi task muốn kiểm soát việc khởi tạo đối tượng hoặc cần trả về một object có sẵn.
- Chọn `addX` khi task chỉ cần nhận và lưu đối tượng; việc kiểm tra có thể thực hiện trong `execute()`.
- Chọn `addConfiguredX` khi cần kiểm tra các thuộc tính hoặc phần tử con ngay sau khi Ant cấu hình xong.
- Với một tên phần tử lồng, chọn một cơ chế rõ ràng và không trộn các phương thức nhận cùng loại phần tử nếu không có chủ đích.

Không có quy tắc rằng mọi task phải dùng `addConfigured`. Chọn phương thức dựa trên việc task cần tạo object, lưu object hay xác thực object sau khi cấu hình.

## 7. Kết hợp thuộc tính XML và phần tử lồng

Một task có thể hỗ trợ thuộc tính ở phần tử gốc và các phần tử con cùng lúc.

Ví dụ:

~~~xml
<report title="Monthly billing"
        output="build/reports/monthly.xml">
    <item name="summary" path="reports/summary.xml" />
    <item name="detail" path="reports/detail.xml" />
</report>
~~~

Lớp task có thể có setter cho thuộc tính gốc:

~~~java
public void setTitle(String title) {
    this.title = title;
}

public void setOutput(String output) {
    this.output = output;
}
~~~

Và có phương thức tiếp nhận phần tử con:

~~~java
public void addConfiguredItem(ItemSpec item) {
    item.validate();
    items.add(item);
}
~~~

Trong ví dụ, Ant ánh xạ:

- `title` tới `setTitle(String)` trên ReportTask.
- `output` tới `setOutput(String)` trên ReportTask.
- Mỗi `item` tới `addConfiguredItem(ItemSpec)`.
- `name` và `path` của item tới setter tương ứng trên ItemSpec.

Điều này giúp XML thể hiện rõ cấu trúc dữ liệu thay vì phải mã hóa tất cả trong một chuỗi.

## 8. Xây dựng một nested element có cấu trúc riêng

Phần tử lồng có thể là một bean Java độc lập. Ví dụ:

~~~java
public static class ItemSpec {

    private String name;
    private String path;
    private boolean required = true;

    public void setName(String name) {
        this.name = name;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public void setRequired(boolean required) {
        this.required = required;
    }

    public String getName() {
        return name;
    }

    public String getPath() {
        return path;
    }

    public boolean isRequired() {
        return required;
    }

    public void validate() {
        if (name == null || name.trim().isEmpty()) {
            throw new BuildException("Item name is required");
        }

        if (required && (path == null || path.trim().isEmpty())) {
            throw new BuildException("Required item needs a path: " + name);
        }
    }
}
~~~

XML tương ứng:

~~~xml
<report>
    <item name="summary"
          path="reports/summary.xml"
          required="true" />
    <item name="optional-chart"
          path="reports/chart.xml"
          required="false" />
</report>
~~~

Ant chuyển các giá trị XML sang kiểu Java theo setter. Thuộc tính boolean `required` được chuyển thành boolean. Các kiểu được hỗ trợ chuyển đổi phụ thuộc introspection và converter của Ant; với kiểu dữ liệu đặc biệt, có thể cần setter nhận String rồi tự parse hoặc cung cấp cơ chế chuyển đổi thích hợp.

Nếu dùng `addConfiguredItem`, task có thể gọi `item.validate()` sau khi tất cả thuộc tính đã được gán:

~~~java
public void addConfiguredItem(ItemSpec item) {
    item.validate();
    items.add(item);
}
~~~

Cách này giữ logic xác thực của chính item trong lớp ItemSpec và để task cha quản lý danh sách các item hợp lệ.

## 9. Phần tử lồng có phần tử con bên trong

Một nested element có thể tiếp tục nhận các phần tử lồng. Ví dụ:

~~~xml
<report>
    <item name="summary" path="reports/summary.xml">
        <column name="customer" />
        <column name="amount" />
    </item>
</report>
~~~

Lớp ItemSpec có thể cung cấp:

~~~java
private final List<ColumnSpec> columns = new ArrayList<ColumnSpec>();

public void addConfiguredColumn(ColumnSpec column) {
    if (column.getName() == null || column.getName().trim().isEmpty()) {
        throw new BuildException("Column name is required");
    }

    columns.add(column);
}
~~~

Và kiểu dữ liệu con:

~~~java
public static class ColumnSpec {
    private String name;

    public void setName(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

Ant cấu hình cây XML từ ngoài vào trong. Nó tạo item, cấu hình các thuộc tính và phần tử column, sau đó gọi phương thức tiếp nhận item của ReportTask. Vì vậy, khi ReportTask dùng `addConfiguredItem`, danh sách column trong item đã được cấu hình xong.

Đây là lý do `addConfigured` hữu ích với các cấu trúc lồng nhiều tầng: lớp cha có thể nhận một object đã hoàn chỉnh để xác thực quan hệ giữa các trường.

## 10. Đăng ký custom task bằng taskdef

Sau khi viết lớp task, cần biên dịch và đóng gói nó thành JAR để Ant nạp.

Ví dụ đăng ký task:

~~~xml
<taskdef name="report"
         classname="com.example.ant.ReportTask"
         classpath="${basedir}/tools/ant-tasks/report-task.jar" />
~~~

Sau khi đăng ký, build file có thể gọi:

~~~xml
<report title="Monthly billing"
        output="build/reports/monthly.xml">
    <item name="summary" path="reports/summary.xml" />
</report>
~~~

JAR custom task cần chứa lớp ReportTask và các lớp nested element như ItemSpec nếu chúng được biên dịch thành class riêng. Nếu task phụ thuộc vào thư viện khác, những thư viện đó cũng phải có trong classpath của taskdef.

Lớp custom task được biên dịch dựa trên API Ant tương thích với môi trường chạy. Ant runtime đã cung cấp các lớp core của Ant; không đóng gói một bản ant.jar khác vào JAR custom task vì có thể gây xung đột classloader hoặc trùng lớp. Khi build custom task, cấu hình compile classpath trỏ tới thư viện Ant phù hợp của môi trường build.

## 11. Tách cấu hình khỏi công việc trong execute

Các phương thức `setX`, `addText`, `createX`, `addX` và `addConfiguredX` chủ yếu tiếp nhận cấu hình. Phương thức `execute()` là nơi task thực hiện công việc chính.

Một cấu trúc dễ bảo trì:

~~~java
public class ReportTask extends Task {

    private String title;
    private String output;
    private final List<ItemSpec> items = new ArrayList<ItemSpec>();

    public void setTitle(String title) {
        this.title = title;
    }

    public void setOutput(String output) {
        this.output = output;
    }

    public void addConfiguredItem(ItemSpec item) {
        item.validate();
        items.add(item);
    }

    @Override
    public void execute() throws BuildException {
        if (title == null || title.trim().isEmpty()) {
            throw new BuildException("Report title is required");
        }

        if (output == null || output.trim().isEmpty()) {
            throw new BuildException("Report output is required");
        }

        if (items.isEmpty()) {
            throw new BuildException("At least one report item is required");
        }

        log("Creating report: " + title);
        for (ItemSpec item : items) {
            log("Including " + item.getName()
                + " from " + item.getPath());
        }

        // Tạo báo cáo tại output.
    }
}
~~~

Các lợi ích:

- XML được chuyển thành object rõ ràng.
- Mỗi phần tử con có thể tự xác thực cấu hình.
- Task cha kiểm tra các điều kiện tổng thể.
- execute chỉ chạy sau khi Ant đã cấu hình task và nested elements.
- Lỗi cấu hình có thể được báo bằng BuildException với thông điệp cụ thể.

Không thực hiện tác dụng phụ trong setter hoặc create method nếu có thể tránh. Những phương thức này thuộc giai đoạn Ant cấu hình task, chưa phải thời điểm thích hợp để chạy toàn bộ nghiệp vụ.

## 12. Phân biệt lỗi cấu hình với lỗi thực thi

Khi custom task nhận dữ liệu lồng, lỗi có thể xuất hiện ở các thời điểm khác nhau:

| Thời điểm | Ví dụ lỗi | Cách xử lý |
|---|---|---|
| Ant introspection | Không tìm thấy create/add method phù hợp | Kiểm tra tên phương thức và kiểu tham số |
| Tạo nested object | Không thể khởi tạo lớp phần tử lồng | Kiểm tra constructor, visibility và kiểu trả về |
| Gán thuộc tính | Không có setter tương ứng hoặc không chuyển đổi được kiểu | Kiểm tra tên setter và kiểu dữ liệu |
| addText | Task không hỗ trợ văn bản trực tiếp | Thêm public addText(String) hoặc sửa XML |
| addX | Phương thức nhận object trước khi cấu hình xong | Không đọc thuộc tính tại thời điểm add |
| addConfiguredX | Validation phát hiện thiếu hoặc sai dữ liệu | Sửa XML hoặc thông báo lỗi rõ ràng |
| execute | Dữ liệu hợp lệ về cấu trúc nhưng công việc thất bại | Xử lý BuildException và log nguyên nhân |

Khi lỗi xảy ra, Ant thường báo tên task, phần tử lồng hoặc thuộc tính liên quan. Hãy xác định lỗi xảy ra trong giai đoạn introspection, cấu hình hay execute trước khi thay đổi mã Java.

## 13. Các quy tắc triển khai và lưu ý về API

- Phương thức nhận cấu hình cần có visibility public để Ant introspection gọi được.
- `addText` nhận một String và xử lý phần văn bản trực tiếp.
- `createX` không có tham số và trả về đối tượng cho phần tử lồng X.
- `addX` nhận một đối tượng X do Ant tạo và chuyển cho task.
- `addConfiguredX` nhận X sau khi Ant đã cấu hình phần tử.
- Lớp nested element cần có khả năng truy cập phù hợp và thường dùng constructor không tham số công khai.
- Các thuộc tính XML được ánh xạ tới setter Java tương ứng.
- Phần tử con lồng sâu hơn được cấu hình trước khi đối tượng cha được chuyển qua addConfigured.
- Kiểm tra dữ liệu sau khi nó đã được cấu hình hoàn chỉnh.
- Dùng BuildException để báo lỗi cấu hình hoặc thực thi theo cách Ant hiểu được.
- Tránh thực hiện công việc có side effect trong setter, create hoặc add.
- Không khai báo nhiều cách tiếp nhận cùng một tên phần tử nếu chưa có lý do và chưa hiểu quy tắc lựa chọn của Ant.

Các chi tiết introspection có thể phụ thuộc phiên bản Ant và kiểu data type được dùng. Khi triển khai custom task cho một phiên bản Ant cụ thể, hãy đối chiếu tài liệu API tương ứng và thử bằng một build file nhỏ trước khi tích hợp vào quy trình lớn.

## 14. Ví dụ tổng hợp: task nhận text và danh sách item

Ví dụ XML:

~~~xml
<report title="Monthly billing"
        output="build/reports/monthly.txt">
    Monthly report generated by Ant.

    <item name="summary" path="reports/summary.xml" />
    <item name="detail" path="reports/detail.xml" />
</report>
~~~

Lớp task có thể kết hợp `addText` và `addConfiguredItem`:

~~~java
public class ReportTask extends Task {

    private String title;
    private String output;
    private final StringBuilder description = new StringBuilder();
    private final List<ItemSpec> items = new ArrayList<ItemSpec>();

    public void setTitle(String title) {
        this.title = title;
    }

    public void setOutput(String output) {
        this.output = output;
    }

    public void addText(String text) {
        description.append(text);
    }

    public void addConfiguredItem(ItemSpec item) {
        item.validate();
        items.add(item);
    }

    @Override
    public void execute() throws BuildException {
        if (title == null || title.trim().isEmpty()) {
            throw new BuildException("Report title is required");
        }

        if (output == null || output.trim().isEmpty()) {
            throw new BuildException("Report output is required");
        }

        if (items.isEmpty()) {
            throw new BuildException("At least one item is required");
        }

        log("Title: " + title);
        log("Description: " + description.toString().trim());

        for (ItemSpec item : items) {
            log("Item " + item.getName() + ": " + item.getPath());
        }

        // Ghi báo cáo vào output.
    }

    public static class ItemSpec {
        private String name;
        private String path;

        public void setName(String name) {
            this.name = name;
        }

        public void setPath(String path) {
            this.path = path;
        }

        public String getName() {
            return name;
        }

        public String getPath() {
            return path;
        }

        public void validate() {
            if (name == null || name.trim().isEmpty()) {
                throw new BuildException("Item name is required");
            }

            if (path == null || path.trim().isEmpty()) {
                throw new BuildException("Item path is required: " + name);
            }
        }
    }
}
~~~

Ví dụ này kết hợp ba cách nhận dữ liệu:

- Setter nhận thuộc tính của phần tử gốc.
- addText nhận phần văn bản trực tiếp trong thân task.
- addConfiguredItem nhận từng phần tử con sau khi nó được cấu hình.

Nếu cần task tự tạo từng item, có thể thay `addConfiguredItem` bằng `createItem()` và lưu đối tượng được tạo. Nếu muốn nhận object trước rồi xử lý sau, dùng `addItem`. Không cần triển khai cả ba cách cho cùng một phần tử nếu không có mục đích rõ ràng.

## 15. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Ant báo task không hỗ trợ nested text | Thiếu phương thức addText(String) | Thêm addText hoặc chuyển nội dung thành thuộc tính/phần tử con |
| Text nhận được có nhiều khoảng trắng | XML có xuống dòng và thụt lề | Trim nếu dữ liệu không cần giữ định dạng; nếu cần thì giữ nguyên |
| Không tìm thấy nested element item | Thiếu createItem/addItem/addConfiguredItem hoặc sai tên | Kiểm tra quy tắc ánh xạ tên XML sang Java method |
| createItem trả về object nhưng thuộc tính luôn null trong create | Ant gọi create trước khi gán thuộc tính | Chỉ tạo/lưu object trong create; kiểm tra sau khi cấu hình |
| addItem thấy name hoặc path là null | add được gọi trước khi nested element cấu hình xong | Chỉ lưu object và kiểm tra trong execute, hoặc dùng addConfiguredItem |
| addConfiguredItem không được gọi | Tên method hoặc kiểu tham số không khớp phần tử | Kiểm tra chính xác tên XML, method và kiểu class |
| Không thể tạo nested object | Lớp không truy cập được hoặc không có constructor phù hợp | Dùng lớp public và constructor không tham số phù hợp |
| Không gán được thuộc tính XML | Thiếu setter hoặc kiểu dữ liệu không chuyển đổi được | Thêm setter public và kiểm tra kiểu |
| Phần tử con sâu hơn chưa có dữ liệu khi validate | Validation chạy ở cấp quá sớm | Xác thực object cha trong addConfigured của cấp cha |
| ClassNotFoundException khi taskdef | JAR custom task hoặc dependency thiếu trong classpath | Kiểm tra taskdef classpath và nội dung JAR |
| Task hoạt động local nhưng lỗi trên CI | Phiên bản Ant hoặc JAR custom task không đồng nhất | Cố định toolchain và chạy cùng build file trên CI |

## 16. Nguyên tắc thiết kế

- Dùng `addText(String)` cho nội dung văn bản trực tiếp, đơn giản.
- Dùng phần tử lồng khi dữ liệu có cấu trúc hoặc có nhiều thuộc tính.
- Dùng `createX()` khi task cần tự tạo đối tượng nested element.
- Dùng `addX(X)` khi task chỉ cần tiếp nhận đối tượng và xử lý sau.
- Dùng `addConfiguredX(X)` khi cần xác thực object sau khi Ant đã cấu hình xong.
- Hiểu rõ thứ tự cấu hình để không đọc thuộc tính quá sớm.
- Tách setter và phương thức tiếp nhận dữ liệu khỏi công việc chính trong execute.
- Dùng BuildException với thông báo cụ thể cho lỗi cấu hình và thực thi.
- Giữ nested element class công khai, có setter phù hợp và constructor mà Ant có thể sử dụng.
- Đăng ký custom task bằng taskdef với classpath đầy đủ và phiên bản Ant tương thích.

Cơ chế nhận text và nested element giúp build file Ant biểu đạt dữ liệu của custom task bằng XML tự nhiên. Khi chọn đúng giữa addText, create, add và addConfigured, task có thể nhận cấu hình rõ ràng, kiểm tra dữ liệu đúng thời điểm và giữ phần thực thi trong execute dễ hiểu, dễ bảo trì.

