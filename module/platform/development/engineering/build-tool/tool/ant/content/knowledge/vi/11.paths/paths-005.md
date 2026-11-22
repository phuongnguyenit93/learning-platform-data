# Chuyển đổi đường dẫn bằng pathconvert và định dạng theo hệ điều hành trong Apache Ant

Trong Apache Ant, một đường dẫn có thể được biểu diễn dưới dạng cấu trúc dữ liệu gồm nhiều file và thư mục. Cấu trúc này thuận tiện khi build cần classpath, danh sách thư viện hoặc tập thư mục nguồn. Tuy nhiên, khi truyền đường dẫn sang chương trình khác, in ra log hoặc ghi vào file cấu hình, đôi khi bạn cần một chuỗi văn bản có dấu phân cách phù hợp với hệ điều hành đích.

Task **pathconvert** nhận dữ liệu đường dẫn của Ant, chuyển thành chuỗi và lưu vào property. Bạn có thể chọn định dạng cho Windows, Unix hoặc hệ điều hành khác, tự đặt dấu phân cách giữa các phần tử và chuẩn hóa đường dẫn bằng quy tắc ánh xạ.

## 1. Vì sao cần chuyển đổi đường dẫn?

Một classpath thường gồm nhiều thư mục và file JAR. Cấu trúc path của Ant cho phép khai báo các phần tử mà không phải tự nối chuỗi:

~~~xml
<path id="compile.path">
    <pathelement location="build/classes"/>
    <pathelement location="lib/core.jar"/>
    <pathelement location="lib/logging.jar"/>
</path>
~~~

Khi task như javac nhận path, Ant có thể sử dụng cấu trúc này trực tiếp:

~~~xml
<javac srcdir="src" destdir="build/classes">
    <classpath refid="compile.path"/>
</javac>
~~~

Nhưng có lúc bạn cần một chuỗi đơn, ví dụ để truyền cho chương trình bên ngoài, in ra log hoặc ghi vào cấu hình. Một chuỗi đường dẫn phụ thuộc hệ điều hành:

| Thành phần | Windows | Unix/Linux |
|---|---|---|
| Dấu phân cách giữa các mục trong classpath | dấu chấm phẩy | dấu hai chấm |
| Dấu phân cách thư mục | dấu gạch chéo ngược | dấu gạch chéo xuôi |
| Ví dụ classpath | lib\core.jar;lib\logging.jar | lib/core.jar:lib/logging.jar |

Hai loại dấu phân cách này có vai trò khác nhau:

- **Path separator** phân tách các phần tử độc lập trong danh sách đường dẫn.
- **Directory separator** phân tách các cấp thư mục bên trong một đường dẫn.

Nhầm lẫn hai loại dấu phân cách là lỗi phổ biến khi tạo classpath bằng cách nối chuỗi thủ công. Task pathconvert cho phép kiểm soát riêng hai thành phần này.

## 2. pathconvert làm gì?

Task pathconvert chuyển một cấu trúc đường dẫn của Ant thành một chuỗi. Nguồn dữ liệu thường là path, nhưng có thể sử dụng các phần tử đường dẫn tương thích như pathelement, fileset, dirset hoặc filelist.

Kết quả thường được lưu trong một property để những task sau sử dụng:

~~~xml
<pathconvert property="compile.classpath.text">
    <path refid="compile.path"/>
</pathconvert>

<echo message="Classpath: ${compile.classpath.text}"/>
~~~

Ở đây:

- compile.path là cấu trúc path đã khai báo trước.
- pathconvert duyệt các phần tử của path và tạo chuỗi biểu diễn.
- compile.classpath.text là property nhận chuỗi kết quả.
- echo in chuỗi để người dùng quan sát.

pathconvert **chuyển cách biểu diễn dữ liệu đường dẫn**. Nó không sao chép file, không tạo thư mục và không biến một file thành file khác.

### 2.1. Cú pháp cơ bản

~~~xml
<pathconvert property="property.name">
    <path refid="path.id"/>
</pathconvert>
~~~

Có thể khai báo cấu trúc path ngay bên trong task:

~~~xml
<pathconvert property="library.list">
    <path>
        <pathelement location="lib/core.jar"/>
        <pathelement location="lib/logging.jar"/>
    </path>
</pathconvert>
~~~

Cách đầu tiên phù hợp khi path đã được khai báo và cần dùng lại. Cách thứ hai tiện khi danh sách đường dẫn chỉ phục vụ một lần chuyển đổi.

### 2.2. Các thuộc tính quan trọng

| Thuộc tính | Ý nghĩa |
|---|---|
| property | Tên property nhận chuỗi đường dẫn sau chuyển đổi. |
| targetos | Hệ điều hành đích dùng để chọn quy tắc dấu phân cách mặc định. |
| pathsep | Ký tự phân cách giữa các phần tử đường dẫn trong chuỗi kết quả. |
| dirsep | Ký tự phân cách các cấp thư mục bên trong mỗi đường dẫn. |
| setonempty | Có đặt property khi path không chứa phần tử nào hay không. |
| preserveduplicates | Có giữ lại các phần tử đường dẫn trùng lặp hay loại bỏ chúng. |

Nếu không chỉ định quy tắc riêng, Ant sử dụng định dạng mặc định theo môi trường đang chạy. Khi cần chuỗi có định dạng dành cho hệ điều hành khác, hãy chỉ định targetos hoặc đặt rõ pathsep và dirsep.

Property của Ant tuân theo nguyên tắc first definition wins. Vì vậy, nên dùng tên property mới cho mỗi lần chuyển đổi với định dạng khác nhau.

## 3. Chọn định dạng theo hệ điều hành bằng targetos

### 3.1. targetos tự chọn hai loại dấu phân cách

Thuộc tính targetos cho biết chuỗi kết quả được định dạng cho hệ điều hành nào. Ant chọn dấu phân cách giữa các phần tử và dấu phân cách thư mục theo hệ điều hành đích.

Ví dụ chuyển path sang định dạng Unix:

~~~xml
<pathconvert
    property="classpath.unix"
    targetos="unix">
    <path refid="compile.path"/>
</pathconvert>
~~~

Chuyển cùng path sang định dạng Windows:

~~~xml
<pathconvert
    property="classpath.windows"
    targetos="windows">
    <path refid="compile.path"/>
</pathconvert>
~~~

Với các đường dẫn tương ứng trong project, kết quả có hình thức minh họa:

~~~text
Unix:
<project-base>/build/classes:<project-base>/lib/core.jar:<project-base>/lib/logging.jar

Windows:
<project-base>\build\classes;<project-base>\lib\core.jar;<project-base>\lib\logging.jar
~~~

Phần project-base biểu thị thư mục cơ sở thực tế của project; đường dẫn kết quả cụ thể phụ thuộc vị trí build file và cách các phần tử path được khai báo.

### 3.2. Các giá trị targetos

Ant hỗ trợ các tên hệ điều hành đích thường gặp như:

- windows
- unix
- netware
- os/2
- tandem
- openvms
- mac

Các định dạng cũ vẫn có thể xuất hiện trong build file dùng chung với môi trường đặc thù. Trong project hiện đại, hai lựa chọn thường gặp nhất là Windows và Unix.

Tên targetos là giá trị định dạng mà pathconvert nhận diện. Hãy dùng đúng tên được task hỗ trợ; không thay bằng tên tùy ý như linux-server hoặc my-os.

### 3.3. targetos không thay đổi hệ điều hành đang chạy

Ví dụ:

~~~xml
<pathconvert
    property="remote.classpath"
    targetos="unix">
    <path refid="compile.path"/>
</pathconvert>
~~~

Lệnh này yêu cầu pathconvert tạo chuỗi theo quy tắc Unix. Nó không chuyển máy đang chạy Ant sang Unix và cũng không cài đặt hay di chuyển các thư viện sang máy Unix.

Nếu build chạy trên Windows nhưng tạo lệnh hoặc cấu hình dành cho môi trường Unix, targetos giúp định dạng chuỗi phù hợp với bên nhận. Tuy nhiên, việc các file thực sự tồn tại ở vị trí tương ứng trên hệ thống đích là vấn đề riêng mà build phải bảo đảm.

## 4. Tự đặt pathsep và dirsep

targetos tiện lợi khi muốn dùng bộ quy tắc chuẩn. Trong một số trường hợp, bạn chỉ muốn thay đổi một dấu phân cách hoặc định dạng theo quy ước riêng. Khi đó, có thể đặt pathsep và dirsep trực tiếp.

### 4.1. pathsep: dấu phân cách giữa các phần tử

Ví dụ:

~~~xml
<pathconvert
    property="classpath.semicolon"
    pathsep=";">
    <path refid="compile.path"/>
</pathconvert>
~~~

Chuỗi kết quả dùng dấu chấm phẩy giữa các mục, bất kể giá trị mặc định của hệ điều hành đang chạy.

Tương tự, có thể dùng dấu hai chấm:

~~~xml
<pathconvert
    property="classpath.colon"
    pathsep=":">
    <path refid="compile.path"/>
</pathconvert>
~~~

Hãy chọn dấu phân cách theo định dạng mà chương trình nhận chuỗi yêu cầu. Ví dụ, classpath của Java trên Windows dùng dấu chấm phẩy, còn trên Unix/Linux dùng dấu hai chấm.

### 4.2. dirsep: dấu phân cách cấp thư mục

Ví dụ buộc các đường dẫn dùng dấu gạch chéo xuôi:

~~~xml
<pathconvert
    property="classpath.forward.slash"
    dirsep="/">
    <path refid="compile.path"/>
</pathconvert>
~~~

Hoặc buộc dùng dấu gạch chéo ngược:

~~~xml
<pathconvert
    property="classpath.back.slash"
    dirsep="\">
    <path refid="compile.path"/>
</pathconvert>
~~~

dirsep chỉ điều khiển dấu phân cách bên trong đường dẫn. Nó không thay đổi dấu phân cách giữa các phần tử trong danh sách.

### 4.3. Kết hợp pathsep và dirsep

Có thể đặt cả hai:

~~~xml
<pathconvert
    property="classpath.custom"
    pathsep=";"
    dirsep="/">
    <path refid="compile.path"/>
</pathconvert>
~~~

Chuỗi kết quả có dạng:

~~~text
<path-1>/<folder>/<file.jar>;<path-2>/<folder>/<file.jar>
~~~

Đây là định dạng tùy chỉnh: các mục cách nhau bằng dấu chấm phẩy, còn các cấp thư mục cách nhau bằng dấu gạch chéo xuôi.

### 4.4. Thứ tự ưu tiên khi cấu hình

Có thể dùng targetos để chọn bộ quy tắc mặc định, sau đó dùng pathsep hoặc dirsep để ghi đè riêng từng thành phần.

Ví dụ:

~~~xml
<pathconvert
    property="classpath.unix.semicolon"
    targetos="unix"
    pathsep=";">
    <path refid="compile.path"/>
</pathconvert>
~~~

Trong ví dụ này, định dạng thư mục theo Unix, còn các phần tử path được phân tách bằng dấu chấm phẩy do pathsep được chỉ định trực tiếp.

Cách kết hợp này hữu ích khi định dạng đích là một quy ước đặc biệt, không trùng hoàn toàn với định dạng chuẩn của một hệ điều hành.

## 5. Chuyển đổi đường dẫn với map

### 5.1. map dùng để ánh xạ tiền tố đường dẫn

Ngoài dấu phân cách, đôi khi bạn cần thay đổi một phần gốc của đường dẫn. Ví dụ, đường dẫn trong môi trường build nằm dưới một thư mục, còn môi trường triển khai dùng thư mục gốc khác.

Phần tử map cho phép khai báo ánh xạ từ một tiền tố sang tiền tố khác:

~~~xml
<pathconvert property="deployment.classpath" targetos="unix">
    <path refid="compile.path"/>
    <map
        from="/workspace/inventory/lib"
        to="/opt/inventory/lib"/>
</pathconvert>
~~~

Nếu một phần tử path bắt đầu bằng tiền tố from, pathconvert thay phần tiền tố đó bằng giá trị to khi tạo kết quả.

Ví dụ minh họa:

~~~text
Đường dẫn đầu vào:
/workspace/inventory/lib/core.jar

Ánh xạ:
from = /workspace/inventory/lib
to   = /opt/inventory/lib

Đường dẫn sau ánh xạ:
/opt/inventory/lib/core.jar
~~~

map phù hợp khi bạn cần chuyển đổi một gốc đường dẫn đã biết, chẳng hạn từ thư mục workspace sang thư mục cài đặt của môi trường đích.

### 5.2. Ánh xạ nhiều tiền tố

Có thể khai báo nhiều map trong cùng một pathconvert:

~~~xml
<pathconvert property="deployment.classpath" targetos="unix">
    <path refid="compile.path"/>

    <map from="/workspace/inventory/lib"
         to="/opt/inventory/lib"/>

    <map from="/workspace/inventory/classes"
         to="/opt/inventory/classes"/>
</pathconvert>
~~~

Mỗi map mô tả một cặp tiền tố nguồn và đích. Điều này hữu ích khi thư viện và lớp biên dịch nằm ở những thư mục khác nhau trong môi trường triển khai.

Nên khai báo ánh xạ cụ thể, dễ đọc và tránh các tiền tố chồng lấn khó dự đoán. Khi một đường dẫn không khớp với map nào, phần đường dẫn đó được chuyển đổi theo quy tắc định dạng chung.

### 5.3. map không di chuyển file

map chỉ thay đổi chuỗi đường dẫn được tạo ra. Nó không tạo thư mục đích, không sao chép JAR và không kiểm tra rằng file đích có tồn tại.

Nếu cần triển khai thư viện, hãy dùng task thao tác file như copy hoặc các task triển khai phù hợp. pathconvert chỉ giúp tạo biểu diễn đường dẫn theo quy ước mà bước tiếp theo cần.

## 6. setonempty và preserveduplicates

Hai thuộc tính này điều khiển cách pathconvert xử lý danh sách đầu vào đặc biệt.

### 6.1. setonempty

Nếu path không có phần tử nào, setonempty quyết định có tạo property kết quả hay không.

Ví dụ:

~~~xml
<path id="optional.path"/>

<pathconvert
    property="optional.classpath"
    setonempty="false">
    <path refid="optional.path"/>
</pathconvert>
~~~

Với setonempty="false", pathconvert không đặt property optional.classpath khi danh sách đầu vào rỗng. Điều này hữu ích khi sự vắng mặt của đường dẫn có ý nghĩa và task phía sau cần phân biệt property chưa được đặt với property chứa chuỗi rỗng.

Nếu muốn property được đặt ngay cả khi kết quả rỗng, dùng setonempty="true".

Lưu ý rằng property Ant đã có sẵn trước đó không bị xóa chỉ vì pathconvert không đặt giá trị mới. Do nguyên tắc first definition wins, hãy dùng tên property riêng nếu cần kiểm soát trạng thái rõ ràng.

### 6.2. preserveduplicates

Một path có thể chứa cùng một phần tử nhiều lần, chẳng hạn do hai nhóm thư viện cùng thêm một JAR. Thuộc tính preserveduplicates điều khiển việc giữ các phần tử lặp lại trong chuỗi kết quả.

~~~xml
<path id="repeated.path">
    <pathelement location="lib/core.jar"/>
    <pathelement location="lib/logging.jar"/>
    <pathelement location="lib/core.jar"/>
</path>

<pathconvert
    property="classpath.unique"
    preserveduplicates="false">
    <path refid="repeated.path"/>
</pathconvert>
~~~

Với preserveduplicates="false", các mục trùng lặp được loại khỏi kết quả chuyển đổi.

Nếu cần giữ nguyên thứ tự và số lần xuất hiện của từng phần tử, dùng preserveduplicates="true".

Không nên loại trùng một cách máy móc. Một số công cụ có quy tắc xử lý classpath riêng; trước khi loại phần tử lặp, hãy xác định liệu thứ tự và sự lặp lại có mang ý nghĩa với chương trình nhận chuỗi hay không.

## 7. Ví dụ: tạo classpath dành cho Windows và Unix

Giả sử project có cấu trúc:

~~~text
inventory-app/
├── build.xml
├── src/
├── build/
│   └── classes/
└── lib/
    ├── core.jar
    └── logging.jar
~~~

Khai báo path dùng chung:

~~~xml
<path id="compile.path">
    <pathelement location="build/classes"/>
    <pathelement location="lib/core.jar"/>
    <pathelement location="lib/logging.jar"/>
</path>
~~~

Chuyển sang định dạng Unix:

~~~xml
<pathconvert
    property="classpath.unix"
    targetos="unix">
    <path refid="compile.path"/>
</pathconvert>
~~~

Chuyển sang định dạng Windows:

~~~xml
<pathconvert
    property="classpath.windows"
    targetos="windows">
    <path refid="compile.path"/>
</pathconvert>
~~~

Dùng hai property:

~~~xml
<target name="show-classpaths">
    <echo message="Unix classpath: ${classpath.unix}"/>
    <echo message="Windows classpath: ${classpath.windows}"/>
</target>
~~~

Nếu cần chuyển tiếp chuỗi cho công cụ bên ngoài, có thể truyền property phù hợp vào thuộc tính của task đó. Ví dụ dùng echo chỉ để hiển thị chuỗi; trong build thực tế, hãy truyền property cho task nhận định dạng đường dẫn tương ứng.

### 7.1. Tạo cả hai chuỗi trong một lần build

Bạn có thể khai báo hai lần pathconvert từ cùng một path:

~~~xml
<pathconvert property="classpath.unix" targetos="unix">
    <path refid="compile.path"/>
</pathconvert>

<pathconvert property="classpath.windows" targetos="windows">
    <path refid="compile.path"/>
</pathconvert>
~~~

Hai lần chuyển đổi dùng chung cấu trúc dữ liệu nhưng lưu kết quả vào hai property khác nhau. Điều này hữu ích khi build tạo script hoặc file cấu hình cho nhiều nền tảng.

### 7.2. Dùng một định dạng tùy chỉnh

Nếu công cụ đích yêu cầu dấu phân cách riêng, có thể đặt trực tiếp:

~~~xml
<pathconvert
    property="classpath.custom"
    pathsep="|"
    dirsep="/">
    <path refid="compile.path"/>
</pathconvert>
~~~

Chuỗi kết quả có hình thức:

~~~text
<path-1>/<folder>/<file.jar>|<path-2>/<folder>/<file.jar>
~~~

Dấu | ở đây chỉ là ví dụ minh họa. Chỉ sử dụng dấu phân cách này nếu chương trình nhận chuỗi hiểu nó theo đúng quy ước.

## 8. Kết hợp pathconvert với property và target

pathconvert thường được đặt ở cấp project nếu kết quả cần dùng ở nhiều target. Nếu chỉ một target cần chuỗi chuyển đổi, có thể đặt task bên trong target đó.

### 8.1. Chuyển đổi một lần và tái sử dụng

~~~xml
<project name="inventory-app" default="show-classpath" basedir=".">

    <path id="compile.path">
        <pathelement location="build/classes"/>
        <pathelement location="lib/core.jar"/>
        <pathelement location="lib/logging.jar"/>
    </path>

    <pathconvert
        property="compile.classpath.text"
        targetos="unix">
        <path refid="compile.path"/>
    </pathconvert>

    <target name="show-classpath">
        <echo message="${compile.classpath.text}"/>
    </target>

    <target name="package">
        <echo message="Using path: ${compile.classpath.text}"/>
    </target>

</project>
~~~

Khi Ant nạp project, path và pathconvert ở cấp project được xử lý để tạo property. Các target có thể dùng property đó.

### 8.2. Chuyển đổi bên trong target

Nếu chuỗi chỉ cần cho một bước, đặt pathconvert trong target:

~~~xml
<target name="prepare-external-command">
    <pathconvert
        property="external.classpath"
        targetos="windows">
        <path refid="compile.path"/>
    </pathconvert>

    <echo message="External classpath: ${external.classpath}"/>
</target>
~~~

Cách này đặt thao tác chuyển đổi gần nơi sử dụng. Tuy nhiên, property Ant vẫn có tính bất biến: nếu property đã được đặt trước đó, lần chuyển đổi sau không thể ghi đè giá trị cũ theo cách thông thường. Hãy chọn tên property phù hợp với từng cấu hình.

## 9. Xử lý đường dẫn có khoảng trắng và ký tự đặc biệt

Một đường dẫn có thể chứa khoảng trắng:

~~~text
C:\Program Files\Inventory\lib\core.jar
~~~

pathconvert tạo chuỗi đường dẫn, nhưng **không tự động trích dẫn từng phần tử** theo cú pháp của shell hoặc chương trình nhận chuỗi.

Nếu chuỗi kết quả được truyền vào command line, cần xử lý quoting theo quy tắc của shell hoặc task thực thi. Dấu nháy kép quanh toàn bộ classpath không phải lúc nào cũng tương đương với việc trích dẫn từng phần tử; điều đó phụ thuộc cú pháp của chương trình nhận.

Ví dụ một classpath Windows chứa hai đường dẫn có khoảng trắng:

~~~text
C:\Program Files\Inventory\lib\core.jar;C:\Shared Libraries\logging.jar
~~~

Dấu chấm phẩy phân tách hai phần tử classpath. Nếu tự nối và đặt dấu nháy sai vị trí, chương trình có thể hiểu cả chuỗi là một đường dẫn duy nhất hoặc tách sai đối số.

Nên để task nhận classpath xử lý cấu trúc path trực tiếp khi có thể. Chỉ chuyển thành chuỗi khi giao diện của chương trình hoặc file cấu hình thực sự yêu cầu chuỗi.

## 10. Những giới hạn cần hiểu

### 10.1. pathconvert không xác minh file đích trên máy khác

Chọn targetos="unix" không chứng minh rằng đường dẫn tương ứng tồn tại trên máy Unix. Task tạo chuỗi theo quy tắc định dạng; build vẫn phải bảo đảm thư viện và thư mục có mặt ở môi trường đích.

### 10.2. Chuyển dấu phân cách không đồng nghĩa ánh xạ gốc đường dẫn

Đổi dirsep từ dấu gạch chéo ngược sang dấu gạch chéo xuôi chỉ điều chỉnh ký tự phân cách thư mục. Nếu đường dẫn bắt đầu bằng một ổ đĩa Windows nhưng môi trường đích dùng cây thư mục Unix khác, bạn cần map hoặc một cấu hình đường dẫn đích thích hợp.

### 10.3. Path separator khác directory separator

Ví dụ:

~~~text
lib/core.jar;lib/logging.jar
~~~

Dấu chấm phẩy phân tách hai phần tử path trên Windows. Dấu gạch chéo ngược hoặc dấu gạch chéo xuôi phân tách các thư mục bên trong từng phần tử.

Nếu đặt nhầm pathsep thành dấu gạch chéo, danh sách thư viện có thể trở thành một chuỗi không còn phân tách được thành các mục.

### 10.4. Property kết quả không tự cập nhật

Nếu property đích đã được đặt, một lần pathconvert sau đó không thay thế giá trị cũ theo cơ chế property thông thường. Hãy dùng tên property khác nhau cho các kết quả như classpath.unix và classpath.windows.

## 11. Những nhầm lẫn thường gặp

### 11.1. Nghĩ pathconvert chỉ đổi dấu gạch chéo

Task còn nối các phần tử path thành một chuỗi, chọn path separator, xử lý phần tử trùng lặp và có thể ánh xạ tiền tố đường dẫn.

### 11.2. Dùng pathsep thay cho dirsep

pathsep phân tách các phần tử độc lập. dirsep phân tách các cấp thư mục bên trong một phần tử. Hai thuộc tính không thay thế cho nhau.

### 11.3. Nghĩ targetos thay đổi máy chạy Ant

targetos chỉ chọn định dạng chuỗi đầu ra. Nó không thay đổi hệ điều hành, không di chuyển file và không chuyển đổi môi trường thực thi.

### 11.4. Nghĩ map sao chép thư mục

map chỉ ánh xạ tiền tố trong chuỗi đường dẫn. Muốn sao chép file, cần dùng task như copy.

### 11.5. Nghĩ pathconvert kiểm tra thư viện có tồn tại

pathconvert chuyển đổi cấu trúc đường dẫn đã cung cấp. Nếu cần kiểm tra file tồn tại, hãy dùng điều kiện hoặc task phù hợp như available trước khi sử dụng đường dẫn.

### 11.6. Tự nối classpath bằng chuỗi

Tự nối bằng dấu hai chấm hoặc dấu chấm phẩy dễ tạo kết quả sai khi chạy trên nền tảng khác. Nên khai báo path bằng các phần tử Ant rồi dùng pathconvert khi thật sự cần chuỗi.

## 12. Quy trình chọn cấu hình pathconvert

Khi chuyển một path thành chuỗi, hãy quyết định lần lượt:

1. Xác định cấu trúc path đầu vào và các phần tử cần đưa vào kết quả.
2. Xác định hệ điều hành mà chương trình nhận chuỗi sẽ sử dụng.
3. Chọn targetos nếu muốn dùng bộ dấu phân cách chuẩn của hệ điều hành đó.
4. Đặt pathsep hoặc dirsep riêng nếu giao diện chương trình yêu cầu quy ước khác.
5. Dùng map khi cần đổi tiền tố thư mục gốc.
6. Quyết định có giữ phần tử trùng lặp bằng preserveduplicates hay không.
7. Quyết định có đặt property khi path rỗng bằng setonempty hay không.
8. Lưu kết quả vào một property riêng và truyền nó cho đúng task hoặc chương trình nhận.

## 13. Ghi nhớ

- **pathconvert** chuyển cấu trúc đường dẫn của Ant thành một chuỗi văn bản.
- **targetos** chọn định dạng theo hệ điều hành đích, thường là Windows hoặc Unix.
- **pathsep** phân tách các phần tử trong danh sách đường dẫn.
- **dirsep** phân tách các cấp thư mục bên trong từng đường dẫn.
- **map** thay thế một tiền tố đường dẫn bằng tiền tố khác trong chuỗi kết quả.
- **setonempty** điều khiển việc đặt property khi đầu vào rỗng.
- **preserveduplicates** điều khiển việc giữ hay loại bỏ các phần tử lặp.
- pathconvert chỉ định dạng đường dẫn; nó không sao chép file, triển khai thư viện hay xác minh máy đích có các đường dẫn đó.
- Khi có thể, hãy giữ cấu trúc path để task Ant sử dụng trực tiếp; chỉ chuyển sang chuỗi khi một giao diện bên ngoài yêu cầu.

Khi phân biệt đúng path separator và directory separator, đồng thời biết cách dùng targetos, pathsep, dirsep và map, bạn có thể tạo chuỗi classpath hoặc danh sách đường dẫn nhất quán cho nhiều hệ điều hành mà không phải tự nối chuỗi theo từng nền tảng.

