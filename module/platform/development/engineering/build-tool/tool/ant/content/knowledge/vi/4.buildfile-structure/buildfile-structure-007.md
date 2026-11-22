# Namespace XML và định danh task bằng URI

Trong một buildfile của Apache Ant, task thường được viết thành phần tử XML, chẳng hạn `<javac>` hoặc `<copy>`. Buildfile còn có các phần tử cấu trúc như `<project>` và `<target>`. Khi một dự án bổ sung task riêng, task từ thư viện mở rộng hoặc nhiều thư viện cùng có task trùng tên, chỉ dùng tên phần tử sẽ khó phân biệt chúng. XML namespace giải quyết vấn đề đó bằng cách gắn mỗi tên phần tử với một định danh namespace.

Ant sử dụng namespace để phân biệt task và data type theo định danh URI. Nhờ vậy, buildfile có thể dùng nhiều thư viện mở rộng mà không phải đổi tên task theo cách tùy tiện. Muốn cấu hình đúng, cần hiểu rõ ba thành phần: namespace URI, prefix trong XML và tên cục bộ của task.

## 1. Namespace XML là gì?

Trong XML, một tên có prefix thường có dạng `prefix:localName`:

```xml
<company:compile />
```

`company` là prefix, còn `compile` là tên cục bộ (*local name*). Prefix được liên kết với một namespace URI bằng khai báo `xmlns`:

```xml
<project xmlns:company="urn:example:ant:tasks">
    <company:compile />
</project>
```

Khai báo `xmlns:company="urn:example:ant:tasks"` có nghĩa là prefix `company` đại diện cho namespace URI `urn:example:ant:tasks` trong phạm vi phần tử `project` và các phần tử con của nó, trừ khi có khai báo khác ghi đè trong một phạm vi lồng nhau.

XML parser không xem chuỗi `company:compile` là một tên không thể tách rời. Nó phân giải tên đó thành cặp:

```text
namespace URI : urn:example:ant:tasks
local name    : compile
```

Cặp này thường được gọi là *expanded name*, có thể biểu diễn ngắn gọn là `{urn:example:ant:tasks}compile`. Namespace URI xác định nhóm tên; local name xác định phần tử cụ thể bên trong nhóm đó.

### Prefix không phải là namespace identity

Prefix chỉ là bí danh dùng trong cú pháp XML. Có thể đổi `company` thành `build` mà không đổi namespace:

```xml
<project xmlns:build="urn:example:ant:tasks">
    <build:compile />
</project>
```

Hai phần tử sau có cùng expanded name vì chúng dùng cùng URI và cùng local name:

```xml
<company:compile xmlns:company="urn:example:ant:tasks" />
<build:compile xmlns:build="urn:example:ant:tasks" />
```

Ngược lại, hai phần tử có cùng local name nhưng URI khác nhau thuộc hai namespace khác nhau:

```xml
<project
    xmlns:company="urn:example:ant:tasks"
    xmlns:vendor="urn:vendor:ant:tasks">

    <company:compile />
    <vendor:compile />
</project>
```

Ở đây `company:compile` và `vendor:compile` có thể được đăng ký bởi hai thư viện độc lập. Tên cục bộ đều là `compile`, nhưng URI giúp Ant phân biệt hai định nghĩa.

Namespace URI là một định danh. Với các URI thông thường như `urn:example:ant:tasks` hoặc `https://example.com/ant/tasks`, XML parser không truy cập địa chỉ đó để tải mã task. Giá trị URI được dùng để nhận diện namespace. Ant có thêm quy ước riêng cho URI bắt đầu bằng `antlib:`, được giải thích ở phần dưới.

## 2. Ant dùng namespace để định danh task như thế nào?

Các task cốt lõi của Ant thường được viết không có prefix:

```xml
<project name="sample" default="build">
    <target name="build">
        <mkdir dir="build/classes" />
        <echo message="Building project" />
    </target>
</project>
```

Đây là các tên task trong namespace mặc định của Ant. Khi dùng task mở rộng, buildfile có thể đặt chúng trong namespace riêng bằng prefix. Việc khai báo prefix mới chỉ thiết lập cách viết tên XML; nó chưa cung cấp implementation cho task. Ant vẫn cần biết task tương ứng với URI và local name đó được định nghĩa ở đâu.

Có hai phần phải khớp nhau:

1. Khai báo namespace trong XML, ví dụ `xmlns:company="urn:example:ant:tasks"`.
2. Đăng ký task trong Ant với cùng URI, ví dụ `uri="urn:example:ant:tasks"`.

Ví dụ đăng ký trực tiếp một task bằng `taskdef`:

```xml
<project name="custom-task-example"
         default="demo"
         xmlns:company="urn:example:ant:tasks">

    <taskdef
        name="hello"
        classname="com.example.ant.HelloTask"
        uri="urn:example:ant:tasks">
        <classpath>
            <pathelement location="lib/company-ant-tasks.jar" />
        </classpath>
    </taskdef>

    <target name="demo">
        <company:hello message="Hello from a custom Ant task" />
    </target>
</project>
```

Trong ví dụ này:

- `xmlns:company` ánh xạ prefix `company` tới URI `urn:example:ant:tasks`.
- `name="hello"` đặt local name cho task.
- `classname` chỉ ra lớp Java triển khai task.
- `uri` gắn task definition với namespace URI.
- `classpath` giúp Ant tìm JAR chứa lớp task và các lớp phụ thuộc cần thiết.
- `<company:hello>` sử dụng đúng URI và local name đã đăng ký.

Nếu bỏ `uri` khỏi định nghĩa `taskdef`, task thường được đăng ký trong namespace mặc định. Khi đó, lời gọi `<company:hello>` không khớp với định nghĩa không namespace. Tương tự, nếu URI trong `taskdef` khác URI trong `xmlns:company`, Ant không thể xem chúng là cùng một task definition.

`taskdef` dùng để đăng ký task. Với data type mở rộng, Ant có cơ chế tương ứng là `typedef`. Cả hai đều có thể gắn định nghĩa với namespace URI để tránh xung đột tên.

## 3. Vì sao phải dùng URI thay vì chỉ dùng prefix?

Prefix phụ thuộc vào cách người viết buildfile chọn tên và phạm vi khai báo. Thư viện không nên phụ thuộc vào bí danh mà người dùng chọn trong file XML. URI cung cấp định danh ổn định hơn.

Ví dụ, một nhóm có thể dùng prefix `company`:

```xml
<project xmlns:company="urn:example:ant:tasks">
    <company:hello />
</project>
```

Nhóm khác có thể thích prefix ngắn hơn:

```xml
<project xmlns:c="urn:example:ant:tasks">
    <c:hello />
</project>
```

Hai buildfile vẫn tham chiếu cùng task definition nếu URI và local name giữ nguyên. Vì thế, khi đăng ký task, thuộc tính `uri` phải nhận giá trị URI đầy đủ, không nhận tên prefix:

```xml
<!-- Đúng: dùng URI đã khai báo trong xmlns -->
<taskdef name="hello"
         classname="com.example.ant.HelloTask"
         uri="urn:example:ant:tasks" />
```

`company` chỉ là bí danh trong một tài liệu XML; nó không phải namespace URI. Đổi prefix không yêu cầu đổi đăng ký task, miễn là prefix mới vẫn trỏ tới đúng URI.

## 4. Dùng Antlib để đóng gói nhiều task

Khi thư viện cung cấp nhiều task hoặc data type, khai báo từng `taskdef` trong mọi buildfile sẽ lặp lại cấu hình. Ant hỗ trợ Antlib để đóng gói các định nghĩa vào một resource XML có tên `antlib.xml`.

Giả sử thư viện có cấu trúc JAR như sau:

```text
company-ant-tasks.jar
└── com/
    └── example/
        └── ant/
            ├── HelloTask.class
            └── antlib.xml
```

Nội dung `com/example/ant/antlib.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<antlib>
    <taskdef
        name="hello"
        classname="com.example.ant.HelloTask" />
</antlib>
```

Buildfile có thể khai báo namespace theo quy ước `antlib:`:

```xml
<project name="antlib-example"
         default="demo"
         xmlns:company="antlib:com.example.ant">

    <target name="demo">
        <company:hello />
    </target>
</project>
```

Với URI `antlib:com.example.ant`, Ant có thể tìm descriptor theo package tương ứng là `com/example/ant/antlib.xml` trên classpath. Khi dùng cơ chế tự nạp này, JAR chứa descriptor và các lớp task phải có mặt trong classpath của Ant.

Cũng có thể yêu cầu Ant nạp descriptor một cách tường minh bằng `taskdef`:

```xml
<project name="antlib-explicit"
         default="demo"
         xmlns:company="antlib:com.example.ant">

    <taskdef
        uri="antlib:com.example.ant"
        resource="com/example/ant/antlib.xml" />

    <target name="demo">
        <company:hello />
    </target>
</project>
```

Ở đây `resource` là đường dẫn resource trên classpath, còn `uri` là namespace mà các định nghĩa trong descriptor được đăng ký vào. Hai giá trị có liên hệ theo quy ước Antlib, nhưng chúng phục vụ hai mục đích khác nhau: `resource` giúp tìm file mô tả; `uri` định danh namespace mà buildfile sử dụng.

`antlib:` là quy ước namespace đặc biệt của Ant, không có nghĩa Ant sẽ gửi HTTP request tới một máy chủ. Ví dụ `antlib:com.example.ant` được ánh xạ theo package thành resource trên classpath. Với URI thông thường như `urn:example:ant:tasks`, cần đăng ký task bằng `taskdef` hoặc cơ chế tương ứng để Ant biết implementation.

## 5. Phạm vi khai báo namespace và default namespace

Khai báo namespace có hiệu lực từ phần tử chứa khai báo xuống các phần tử con. Vì vậy, đặt `xmlns:company` trên `project` giúp mọi `target` bên trong sử dụng được prefix đó:

```xml
<project xmlns:company="urn:example:ant:tasks">
    <target name="first">
        <company:hello />
    </target>

    <target name="second">
        <company:hello />
    </target>
</project>
```

Có thể khai báo prefix ở một phần tử con nếu chỉ muốn giới hạn phạm vi sử dụng. Một prefix cũng có thể được khai báo lại trong phạm vi lồng nhau; khi đó khai báo gần phần tử hơn sẽ được áp dụng cho phần tử nằm trong phạm vi đó.

XML còn hỗ trợ default namespace qua thuộc tính `xmlns` không có hậu tố prefix. Tuy nhiên, khi viết Ant buildfile, nên giữ task Ant cốt lõi ở dạng không prefix và dùng prefix riêng cho task mở rộng. Việc đặt default namespace trên `project` có thể khiến những phần tử vốn được hiểu là task cốt lõi bị đưa sang namespace khác, làm Ant không phân giải được chúng như mong muốn.

Ví dụ dễ đọc và ít gây nhầm lẫn:

```xml
<project xmlns:company="urn:example:ant:tasks">
    <target name="build">
        <mkdir dir="build" />
        <company:hello />
    </target>
</project>
```

`target` và `mkdir` vẫn được viết theo cú pháp task cốt lõi; chỉ task mở rộng mới dùng prefix `company`.

## 6. Quy tắc chọn namespace URI

Khi tự thiết kế namespace cho thư viện task, nên chọn URI ổn định, có khả năng phân biệt với thư viện khác và giữ nguyên trong các phiên bản tương thích.

Một số lựa chọn thường gặp:

| Dạng URI | Ví dụ | Cách dùng |
|---|---|---|
| URN tự đặt | `urn:example:ant:tasks` | Định danh namespace rõ ràng; đăng ký trực tiếp bằng `taskdef uri` |
| Antlib theo package | `antlib:com.example.ant` | Dùng quy ước Antlib để tìm `com/example/ant/antlib.xml` trên classpath |
| URI theo tên miền | `https://example.com/ant/tasks` | Có thể dùng làm định danh ổn định; không cần máy chủ phục vụ XML chỉ để parser nhận diện namespace |

Trong dự án thực tế, tránh dùng URI quá chung như `tasks` hoặc `custom`. Một URI có tính duy nhất giúp giảm khả năng hai thư viện vô tình dùng cùng namespace. Khi đã phát hành thư viện, không nên đổi URI tùy tiện vì buildfile của người dùng có thể đang khai báo và tham chiếu URI cũ.

Prefix nên ngắn, dễ hiểu và nhất quán trong cùng buildfile. Prefix có thể khác giữa các dự án; URI mới là giá trị cần được giữ ổn định.

## 7. Lỗi thường gặp khi cấu hình namespace

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Ant không nhận ra phần tử có prefix | Chưa đăng ký task hoặc Antlib chưa được nạp | Kiểm tra `taskdef`, `typedef`, descriptor và classpath |
| Task đã đăng ký nhưng lời gọi có prefix vẫn lỗi | URI trong `xmlns` khác URI trong `taskdef` | So sánh nguyên văn hai giá trị URI |
| Đổi prefix thì buildfile lỗi | Prefix mới chưa được khai báo hoặc khai báo trong phạm vi không bao phủ phần tử | Kiểm tra `xmlns:prefix` trên `project` hoặc phần tử cha phù hợp |
| Task class không được tìm thấy | JAR chứa task không có trong classpath hoặc sai tên lớp | Kiểm tra `classname`, đường dẫn JAR và dependency của task |
| Ant không tìm thấy Antlib descriptor | Resource không nằm đúng đường dẫn hoặc JAR chưa có trên classpath | Kiểm tra `antlib.xml`, đường dẫn resource và package tương ứng với URI `antlib:` |
| Task cốt lõi không còn được phân giải như trước | Default namespace đã làm thay đổi namespace của các phần tử không prefix | Dùng prefix riêng cho task mở rộng và giữ task cốt lõi không prefix |

Khi gặp lỗi, nên lần lượt kiểm tra tên phần tử, prefix, URI được prefix trỏ tới, local name trong định nghĩa và nơi Ant tải implementation. Cách kiểm tra này tách được lỗi cú pháp XML khỏi lỗi đăng ký task hoặc lỗi classpath.

## 8. Trình tự cấu hình một task có namespace

Khi thêm một task mở rộng vào buildfile, có thể thực hiện theo trình tự sau:

1. Xác định task thuộc thư viện nào và thư viện cung cấp task trực tiếp hay qua Antlib.
2. Chọn hoặc đọc namespace URI mà thư viện công bố. Nếu thư viện dùng Antlib, lấy đúng URI `antlib:...` theo package của nó.
3. Khai báo một prefix dễ đọc trên `project` hoặc phần tử cha thích hợp, ví dụ `xmlns:company="urn:example:ant:tasks"`.
4. Đăng ký task bằng `taskdef` với `name`, `classname` và cùng `uri`, hoặc nạp Antlib descriptor tương ứng.
5. Bảo đảm JAR và các dependency cần thiết có trong classpath của Ant.
6. Gọi task bằng phần tử có prefix và local name đúng, ví dụ `<company:hello />`.
7. Chạy buildfile và kiểm tra thông báo lỗi nếu Ant không phân giải được namespace hoặc implementation.

Điểm cần nhớ là định danh task trong namespace được hình thành từ URI và local name. Prefix chỉ giúp viết tên đó trong XML. Khi hai phần này được khai báo nhất quán và implementation đã được nạp, Ant có thể phân biệt task mở rộng với task cùng tên đến từ namespace khác mà buildfile vẫn giữ được cấu trúc XML rõ ràng.
