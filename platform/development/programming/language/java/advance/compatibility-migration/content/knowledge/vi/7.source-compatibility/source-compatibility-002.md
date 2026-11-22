# Import theo ký tự đại diện và tên lớp trùng với API mới

## 1. Vì sao import có thể trở thành vấn đề khi nâng JDK?

Trong Java, câu lệnh import cho phép mã nguồn dùng tên ngắn của kiểu dữ liệu thay vì phải viết đầy đủ tên package. Nhiều dự án sử dụng import theo ký tự đại diện như:

~~~java
import java.util.*;
import com.example.model.*;
~~~

Cách viết này gọn khi package có nhiều kiểu được sử dụng. Tuy nhiên, khi nâng JDK, nền tảng có thể bổ sung một lớp hoặc interface mới có cùng tên đơn giản với kiểu đã tồn tại trong thư viện bên thứ ba hoặc trong một package khác của dự án.

Mã nguồn trước đây có thể biên dịch bình thường vì chỉ có một kiểu mang tên đó trong các import đang dùng. Sau khi chuyển sang JDK mới, kiểu mới của JDK xuất hiện trong phạm vi tra cứu tên và khiến tham chiếu trở nên mơ hồ. Compiler có thể báo lỗi vì không xác định được kiểu nào được dự định sử dụng.

Ví dụ điển hình là:

- Java 9 bổ sung java.lang.Module.
- Java 16 bổ sung java.lang.Record.
- Java 21 bổ sung java.util.SequencedCollection, SequencedSet và SequencedMap.

Những kiểu trong java.lang được import ngầm định vào mọi compilation unit. Vì vậy, xung đột có thể xuất hiện ngay cả khi source code không viết import java.lang.*.

Trong migration, cần kiểm tra import theo ký tự đại diện cùng các tên lớp trùng với API mới, xác định kiểu mà từng chỗ sử dụng cần tham chiếu, rồi sửa import một cách tường minh. Không nên đổi hàng loạt chỉ dựa trên tên lớp vì cùng một tên có thể đại diện cho các API có mục đích và hợp đồng khác nhau.

## 2. Các dạng import trong Java

Java có một số dạng import chính:

| Cú pháp | Ý nghĩa |
|---|---|
| import package.Type; | Import tường minh một kiểu cụ thể. |
| import package.*; | Import theo ký tự đại diện các kiểu truy cập được khai báo trực tiếp trong package. |
| import static package.Type.member; | Import tường minh một thành viên static. |
| import static package.Type.*; | Import theo ký tự đại diện các thành viên static truy cập được của kiểu. |

Ví dụ:

~~~java
import java.util.List;
import java.util.Map;
import java.util.*;

import static java.util.Collections.emptyList;
import static java.util.Collections.*;
~~~

Không cần đồng thời khai báo các import minh họa trên trong cùng một file; chúng được đặt cạnh nhau để cho thấy các hình thức khác nhau.

### 2.1. Import một kiểu tường minh

Import tường minh chỉ định chính xác package và kiểu:

~~~java
import java.util.List;

public class Catalog {
    private List<String> names;
}
~~~

Khi đọc source, người phát triển biết ngay List được lấy từ package nào. Nếu thư viện khác cũng có một kiểu List, import tường minh giúp tránh phải suy luận từ các import theo ký tự đại diện.

Đây là lựa chọn phù hợp khi:

- Kiểu nằm trong public API hoặc chữ ký phương thức.
- Tên kiểu dễ trùng với kiểu trong JDK hoặc thư viện phổ biến.
- Dự án đang nâng JDK và cần kiểm soát rõ kiểu được tham chiếu.
- Một file sử dụng hai kiểu khác package nhưng có cùng tên đơn giản.

### 2.2. Import theo ký tự đại diện

Import theo ký tự đại diện dùng dấu *:

~~~java
import java.util.*;
~~~

Lệnh này cho phép dùng tên đơn giản của các kiểu truy cập được khai báo trực tiếp trong package java.util. Nó không import đệ quy các package con. Ví dụ, import java.util.* không tự động import các kiểu trong java.util.concurrent.

Import theo ký tự đại diện:

- Không làm tăng runtime classpath và không tải tất cả class trong package vào bộ nhớ.
- Không tạo một dependency mới ở runtime.
- Chỉ ảnh hưởng đến việc compiler tra cứu tên trong source code.
- Có thể khiến một tên đơn giản trở nên mơ hồ nếu nhiều import theo ký tự đại diện cung cấp kiểu cùng tên.

Do đó, wildcard import không trực tiếp làm ứng dụng chạy chậm hoặc đóng gói thêm toàn bộ package. Rủi ro chính của nó nằm ở khả năng đọc hiểu và phân giải tên khi package hoặc JDK thay đổi.

### 2.3. Import ngầm định từ java.lang

Các kiểu truy cập được trong java.lang được import ngầm định. Vì thế, source có thể sử dụng String, Object, Thread hoặc Record mà không cần khai báo import java.lang.*.

Khi JDK bổ sung kiểu mới vào java.lang, tên đó cũng tham gia quá trình phân giải tên trong source hiện có. Đây là lý do một import theo ký tự đại diện từ package bên thứ ba có thể xung đột với một API mới của nền tảng dù file không hề khai báo wildcard import cho java.lang.

## 3. Cách compiler phân giải tên kiểu

Để xử lý xung đột đúng, cần hiểu sự khác nhau giữa import tường minh và import theo ký tự đại diện.

### 3.1. Hai wildcard import có cùng tên kiểu

Giả sử hai package đều có kiểu tên Record:

~~~java
import com.legacy.model.*;
import com.reporting.model.*;

public class ReportService {
    private Record record;
}
~~~

Nếu cả hai package đều có kiểu truy cập được mang tên Record, compiler không thể tự chọn một kiểu. Tham chiếu Record bị mơ hồ và source không biên dịch được.

Classpath order không phải cách giải quyết xung đột này. Việc đổi thứ tự hai dòng import cũng không làm cho một package được ưu tiên.

### 3.2. Import tường minh và wildcard import

Một import kiểu tường minh giúp chỉ rõ kiểu được dự định sử dụng:

~~~java
import com.legacy.model.Record;
import com.reporting.model.*;

public class ReportService {
    private Record record;
}
~~~

Ở đây, tên đơn giản Record được xác định bằng import tường minh. Wildcard import còn lại vẫn có thể được dùng cho các kiểu khác trong package.

Nếu cần dùng cả hai kiểu cùng tên trong một file, Java không có cú pháp import alias như một số ngôn ngữ khác. Có thể import một kiểu và dùng tên đầy đủ cho kiểu còn lại:

~~~java
import com.legacy.model.Record;

public class ReportService {
    private Record sourceRecord;
    private com.reporting.model.Record outputRecord;
}
~~~

Nếu hai kiểu đều chỉ xuất hiện một vài lần, dùng tên đầy đủ tại nơi sử dụng có thể làm ý định rõ ràng hơn việc tạo nhiều wildcard import.

### 3.3. Hai import tường minh có cùng tên đơn giản

Nếu khai báo hai import tường minh cho hai kiểu khác nhau nhưng cùng tên đơn giản:

~~~java
import java.util.Date;
import java.sql.Date;
~~~

Đây là xung đột trong cùng compilation unit. Cần bỏ một import và dùng tên đầy đủ cho kiểu còn lại:

~~~java
import java.util.Date;

public class DateConverter {
    private Date instantDate;
    private java.sql.Date databaseDate;
}
~~~

Không có import alias trong Java để đổi tên một kiểu khi import. Tên đầy đủ là cách trực tiếp để phân biệt hai kiểu có cùng simple name.

### 3.4. Kiểu trong cùng package

Kiểu được khai báo trong cùng package có thể được dùng mà không cần import. Một wildcard import không phải là cách để ghi đè kiểu cùng tên đã được khai báo trong package hiện tại. Khi dự án có kiểu nội bộ trùng tên với API JDK, cần xác định rõ phạm vi và dùng tên đầy đủ nếu cần tham chiếu đến cả hai.

## 4. Các API JDK mới có thể tạo xung đột tên

Tên kiểu mới có thể xuất hiện trong java.lang hoặc trong package được dự án import bằng wildcard. Một số mốc dễ gặp trong quá trình nâng Java:

| Phiên bản Java | API được bổ sung | Vùng tên | Nguy cơ thường gặp |
|---|---|---|---|
| Java 9 | Module | java.lang | Trùng với kiểu Module trong thư viện hoặc package được import theo ký tự đại diện. |
| Java 16 | Record | java.lang | Trùng với kiểu Record trong mô hình dữ liệu hoặc thư viện legacy. |
| Java 21 | SequencedCollection | java.util | Trùng với kiểu cùng tên trong thư viện collection bên thứ ba. |
| Java 21 | SequencedSet | java.util | Trùng với kiểu cùng tên trong package collection khác. |
| Java 21 | SequencedMap | java.util | Trùng với kiểu cùng tên trong package map hoặc thư viện khác. |

Danh sách trên là ví dụ tiêu biểu, không phải danh mục đầy đủ mọi API được bổ sung qua các phiên bản Java. Khi migration, hãy đối chiếu release notes và API documentation của JDK mục tiêu với tên kiểu thực tế trong dependency graph của dự án.

### 4.1. Ví dụ: Record sau Java 16

Giả sử ứng dụng có kiểu riêng:

~~~java
package com.legacy.model;

public class Record {
    private String id;
}
~~~

Một file khác sử dụng wildcard import:

~~~java
import com.legacy.model.*;

public class RecordService {
    private Record current;
}
~~~

Từ Java 16, java.lang.Record tồn tại và được import ngầm định. Tên Record đồng thời có thể được cung cấp bởi wildcard import com.legacy.model.*. Khi cả hai kiểu cùng tham gia tra cứu, compiler có thể báo tên kiểu mơ hồ.

Nếu mục đích là dùng kiểu dữ liệu legacy, hãy import rõ:

~~~java
import com.legacy.model.Record;

public class RecordService {
    private Record current;
}
~~~

Nếu cần tham chiếu cả lớp nền tảng java.lang.Record, dùng tên đầy đủ:

~~~java
private com.legacy.model.Record legacyRecord;
private java.lang.Record javaRecord;
~~~

java.lang.Record là lớp nền tảng cho các record class của ngôn ngữ Java. Nó không có cùng ý nghĩa nghiệp vụ với một lớp Record do ứng dụng tự định nghĩa. Không thay kiểu này bằng kiểu kia chỉ để compiler hết báo lỗi.

### 4.2. Ví dụ: Module sau Java 9

Java 9 bổ sung java.lang.Module để đại diện cho module runtime. Nếu một thư viện legacy cũng cung cấp com.legacy.runtime.Module và source dùng wildcard import:

~~~java
import com.legacy.runtime.*;

public class RuntimeInspector {
    private Module current;
}
~~~

Tên Module có thể xung đột với java.lang.Module được import ngầm định. Hãy xác định ý nghĩa của biến:

~~~java
import com.legacy.runtime.Module;

public class RuntimeInspector {
    private Module legacyModule;
    private java.lang.Module platformModule;
}
~~~

Tên biến cũng nên phản ánh vai trò để người đọc không nhầm module nghiệp vụ với module của Java Platform Module System.

### 4.3. Ví dụ: SequencedCollection sau Java 21

Java 21 bổ sung SequencedCollection, SequencedSet và SequencedMap trong java.util. Các kiểu này mô tả collection có thứ tự gặp phần tử đầu và cuối, đồng thời cung cấp các thao tác đầu/cuối thống nhất.

Giả sử một thư viện collection bên thứ ba cũng cung cấp kiểu SequencedCollection:

~~~java
import java.util.*;
import com.vendor.collections.*;

public class SequenceService {
    private SequencedCollection<String> values;
}
~~~

Trên một JDK trước Java 21, java.util chưa có SequencedCollection nên tên đơn giản có thể chỉ đến kiểu của thư viện. Khi biên dịch với API Java 21, cả hai wildcard import đều có thể cung cấp kiểu cùng tên và tham chiếu trở nên mơ hồ.

Nếu ứng dụng muốn dùng kiểu chuẩn của JDK:

~~~java
import java.util.SequencedCollection;
import com.vendor.collections.*;

public class SequenceService {
    private SequencedCollection<String> values;
}
~~~

Nếu ứng dụng cần kiểu của thư viện:

~~~java
import com.vendor.collections.SequencedCollection;

public class SequenceService {
    private SequencedCollection<String> values;
}
~~~

Nếu cần dùng cả hai:

~~~java
public class SequenceService {
    private java.util.SequencedCollection<String> platformValues;
    private com.vendor.collections.SequencedCollection<String> vendorValues;
}
~~~

Ví dụ dùng package com.vendor.collections là giả định minh họa xung đột tên. Khi xử lý dự án thật, cần thay bằng package và kiểu có trong dependency thực tế.

## 5. Wildcard import và thay đổi API theo release

Một file có thể biên dịch trên JDK cũ nhưng lỗi trên JDK mới vì tập kiểu có thể truy cập từ thư viện chuẩn đã thay đổi. Cần phân biệt JDK dùng để chạy compiler với release API mà source được phép sử dụng.

### 5.1. Dùng --release khi cần giữ mức API cũ

Tùy chọn --release của javac chọn phiên bản Java làm mục tiêu biên dịch, bao gồm mức ngôn ngữ, bytecode và tập API chuẩn được phép tham chiếu.

Ví dụ, nếu compiler JDK 21 được dùng để biên dịch nhưng ứng dụng vẫn phải tương thích với Java 17:

~~~bash
javac --release 17 -d out -cp "lib/vendor.jar" src/main/java/example/SequenceService.java
~~~

Trong cấu hình này, API java.util.SequencedCollection của Java 21 không thuộc tập API Java 17 được phép dùng. Điều đó có thể tránh việc source vô tình phụ thuộc vào API mới hơn mức hỗ trợ đã cam kết.

Nếu mục tiêu là Java 21:

~~~bash
javac --release 21 -d out -cp "lib/vendor.jar" src/main/java/example/SequenceService.java
~~~

Khi đó API Java 21 được đưa vào phạm vi biên dịch và xung đột tên có thể xuất hiện. Dùng --release không tự giải quyết xung đột giữa hai kiểu cùng tên; nó chỉ xác định tập API chuẩn có thể tham chiếu.

### 5.2. Gradle

Với Gradle, cần cấu hình toolchain và release theo baseline/target của dự án:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ví dụ trên dùng compiler từ JDK 21 nhưng tạo bytecode/API target Java 17. Nếu dự án đã quyết định nâng API target lên Java 21, đổi release tương ứng và kiểm tra các tên kiểu mới xuất hiện trong source.

### 5.3. Maven

Với Maven Compiler Plugin, khai báo release mục tiêu trong cấu hình dự án:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Khi nâng API target lên Java 21, cập nhật release theo mục tiêu đã được thống nhất. Cần kiểm tra cả JDK chạy Maven và cấu hình toolchain nếu Maven sử dụng compiler JDK riêng.

### 5.4. Không dùng --release để che xung đột trong mục tiêu mới

Nếu dự án thực sự cần Java 21, giữ release ở Java 17 chỉ để tránh lỗi import là không giải quyết yêu cầu migration. Cần quyết định kiểu nào được dùng, sửa import và kiểm thử hành vi. Mức release phải phản ánh phiên bản Java thấp nhất mà artifact cần hỗ trợ, không phải một cách tắt tạm thời lỗi biên dịch.

## 6. Import static theo ký tự đại diện

Wildcard import còn xuất hiện trong import static:

~~~java
import static java.util.Collections.*;
import static com.example.CollectionHelpers.*;
~~~

Các dòng này đưa các thành viên static có thể truy cập của hai kiểu vào phạm vi tra cứu tên. Nếu hai nơi cung cấp phương thức cùng tên, lời gọi không có qualifier có thể trở nên khó phân giải hoặc mơ hồ tùy chữ ký và quy tắc overload resolution.

Ví dụ:

~~~java
import static java.lang.Math.*;
import static com.example.NumericHelpers.*;

public class Calculation {
    double result = max(10.0, 20.0);
}
~~~

Nếu cả hai nơi đều cung cấp phương thức max phù hợp với lời gọi, compiler có thể không chọn được một phương thức duy nhất. Cách xử lý là import tường minh thành viên cần dùng hoặc gọi bằng tên lớp:

~~~java
double platformMax = java.lang.Math.max(10.0, 20.0);
double customMax = com.example.NumericHelpers.max(10.0, 20.0);
~~~

Trong migration, cần xem xét static wildcard import khi một JDK mới bổ sung thành viên static hoặc khi nâng thư viện utility. Quy tắc chung vẫn là làm rõ nguồn của thành viên được gọi.

## 7. Cách xử lý xung đột import trong quá trình migration

Khi compiler báo tên kiểu mơ hồ sau khi nâng JDK, xử lý theo một trình tự có thể kiểm chứng:

1. Đọc chính xác thông báo compiler và xác định simple name bị mơ hồ.
2. Liệt kê tất cả package hoặc kiểu có thể cung cấp tên đó, bao gồm java.lang được import ngầm định.
3. Xác định kiểu mà mã nguồn dự định sử dụng dựa trên chữ ký, hành vi, dependency và mục đích nghiệp vụ.
4. Thay wildcard import liên quan bằng import tường minh ở nơi có xung đột.
5. Nếu cùng một file cần cả hai kiểu, dùng tên đầy đủ cho ít nhất một kiểu.
6. Kiểm tra generic type, method parameter/return type, constructor, annotation, cast, static member và test fixture có sử dụng cùng tên.
7. Biên dịch lại bằng release mục tiêu và chạy các test liên quan.

Không nên chỉ sửa dòng khai báo field đang báo lỗi. Cùng simple name có thể xuất hiện ở nhiều vị trí:

~~~java
Record createRecord(Record input) {
    Record copy = new Record();
    return copy;
}
~~~

Phải bảo đảm kiểu của tham số, kiểu trả về, biến cục bộ và constructor đều trỏ đến cùng loại API dự định sử dụng.

### 7.1. Chọn import tường minh cho các kiểu quan trọng

Một quy ước dễ duy trì là import tường minh:

- Các kiểu xuất hiện trong public method signature.
- Các kiểu có tên phổ biến như Date, List, Set, Map, Module, Record, Path, Process hoặc các kiểu mới có khả năng trùng.
- Các kiểu đến từ nhiều thư viện cùng domain.
- Các kiểu xuất hiện trong code được chia sẻ giữa nhiều module.

Wildcard import có thể vẫn được dùng nếu style guide của dự án cho phép và package không tạo ra xung đột. Quan trọng là không để quyết định import phụ thuộc vào thứ tự classpath hoặc giả định rằng package sẽ không có thêm kiểu mới.

### 7.2. Dùng tên đầy đủ khi cần hai kiểu cùng tên

Java không hỗ trợ import alias. Nếu một file thường xuyên sử dụng hai kiểu cùng tên, có thể:

- Import kiểu được dùng nhiều hơn và viết tên đầy đủ cho kiểu còn lại.
- Viết tên đầy đủ cho cả hai tại những vị trí quan trọng.
- Tạo adapter hoặc facade mang tên theo domain để giảm sự lan truyền của kiểu legacy, nếu đó là thay đổi kiến trúc có chủ đích.

Không nên đổi tên một class public hoặc thay đổi package chỉ để giải quyết một lỗi import nếu việc đó phá vỡ API của module khác. Trước tiên hãy xử lý ở phạm vi compilation unit.

### 7.3. Kiểm tra auto-import và organize imports của IDE

IDE có thể tự thêm, xóa hoặc gom import theo cấu hình tối ưu hóa import. Khi nâng JDK hoặc đổi Project SDK:

- Kiểm tra kiểu mà IDE tự chọn khi hoàn thành mã.
- Mở danh sách import sau khi chạy Optimize Imports.
- Kiểm tra wildcard threshold trong code style.
- Đảm bảo IDE Project SDK và compiler/build tool đang dùng cùng release mục tiêu.
- Xem diff sau thao tác organize imports để phát hiện thay đổi ngoài ý muốn.

Không nên để IDE tự chọn một kiểu khi có hai API cùng tên mà không xem lại package. Auto-import là tiện ích chỉnh sửa source, không phải bằng chứng về ý nghĩa nghiệp vụ của kiểu.

## 8. Tìm kiếm các import có rủi ro trong source

Khi bắt đầu migration, có thể tìm wildcard import trong repository để xác định vùng cần rà soát. Ví dụ với ripgrep:

~~~bash
rg -n '^\s*import\s+[\w.]+\.\*;' --glob '*.java'
rg -n '^\s*import\s+static\s+[\w.]+\.\*;' --glob '*.java'
~~~

Kết quả tìm kiếm là danh sách để điều tra, không phải danh sách lỗi. Không phải wildcard import nào cũng gây xung đột. Cần đối chiếu tên kiểu được sử dụng với các API mới và dependency thực tế.

Có thể tìm các tên mới quan trọng trong source:

~~~bash
rg -n '\b(Module|Record|SequencedCollection|SequencedSet|SequencedMap)\b' --glob '*.java'
~~~

Tìm kiếm bằng tên đơn giản có thể trả về comment, string, tên biến hoặc class không liên quan. Hãy kiểm tra từng kết quả để xác định đó có phải type reference hay không.

Với repository nhiều module, thực hiện tìm kiếm trong các source set Java của từng module và ghi nhận module sở hữu file. Không tự động thay toàn bộ wildcard import trong repository chỉ vì một module gặp xung đột.

## 9. Kiểm chứng sau khi sửa import

Sau khi sửa, cần chứng minh source được biên dịch bằng đúng API release và kiểu mong muốn:

### 9.1. Biên dịch bằng JDK mục tiêu

Chạy build chuẩn của dự án với JDK/toolchain đã chọn. Nếu dùng Gradle:

~~~bash
./gradlew clean compileJava
~~~

Nếu dùng Maven:

~~~bash
./mvnw clean compile
~~~

Không chỉ dựa vào IDE báo hết lỗi. Build từ wrapper giúp kiểm tra cấu hình thực tế mà CI sẽ sử dụng.

### 9.2. Kiểm tra chữ ký và hành vi

Nếu kiểu được chọn có API khác với kiểu cũ, hãy xem xét:

- Generic bounds và type inference.
- Method signature, constructor và overload resolution.
- Serialization/deserialization.
- Mapping dữ liệu, persistence và framework binding.
- API public của module hoặc service khác đang phụ thuộc.

Ví dụ, thay một kiểu collection bên thứ ba bằng SequencedCollection của JDK có thể làm thay đổi interface mà các module khác nhìn thấy. Dù tên gọi gần giống nhau, không được giả định hai kiểu có cùng contract, thứ tự iteration, mutability, serialization hoặc khả năng tương thích binary.

### 9.3. Chạy test và xem diff

Chạy unit test và integration test liên quan đến thành phần vừa đổi. Đặc biệt kiểm tra nơi kiểu đó được truyền qua module boundary hoặc serialize thành dữ liệu. Sau đó xem diff để bảo đảm chỉ các import và tham chiếu cần thiết được thay đổi.

## 10. Quy ước phòng ngừa xung đột trong dự án

Để giảm lỗi khi nâng JDK trong tương lai, dự án có thể thống nhất một số quy ước:

- Ưu tiên import tường minh cho kiểu được dùng trong public API và kiểu có tên phổ biến.
- Hạn chế wildcard import ở các package có nhiều kiểu cùng domain hoặc thay đổi thường xuyên.
- Không đặt tên class nghiệp vụ trùng với các kiểu nền tảng phổ biến như Record, Module, Thread, Process hoặc các kiểu collection chuẩn nếu có lựa chọn tên domain rõ hơn.
- Khi buộc phải giữ tên legacy, import rõ package và dùng tên đầy đủ ở nơi cần tham chiếu đến API JDK.
- Giữ compiler release đồng bộ với phiên bản Java thấp nhất mà sản phẩm cam kết hỗ trợ.
- Khi nâng JDK, rà soát release notes/API additions và chạy compile trên JDK mục tiêu.
- Đưa lỗi import ambiguity vào danh sách migration source compatibility để xử lý cùng các lỗi compile khác.

Các quy ước này không nhằm cấm tuyệt đối wildcard import. Chúng giúp source ít phụ thuộc hơn vào việc package hoặc JDK sẽ bổ sung kiểu mới trong tương lai.

## 11. Ví dụ tổng hợp: xử lý xung đột khi nâng Java 17 lên Java 21

Giả sử một ứng dụng có thư viện collection nội bộ và trước đây dùng:

~~~java
import java.util.*;
import com.company.collections.*;

public class OrderedCatalog {
    private SequencedCollection<String> entries;
}
~~~

Ở Java 17, java.util chưa cung cấp SequencedCollection. Nếu thư viện nội bộ có kiểu này, source có thể biên dịch và tên đơn giản được phân giải theo import của thư viện.

Khi nâng compiler/API target lên Java 21, java.util có SequencedCollection. Hai wildcard import giờ có thể cung cấp hai kiểu cùng tên, khiến compiler báo ambiguous reference.

Nhóm migration cần quyết định:

1. Ứng dụng muốn sử dụng API chuẩn Java 21 hay tiếp tục dùng kiểu nội bộ?
2. Nếu chọn API chuẩn, thư viện nội bộ có còn cần thiết không?
3. Các module khác có đang phụ thuộc vào kiểu nội bộ trong public API không?
4. Việc chuyển sang kiểu chuẩn có làm thay đổi hành vi về thứ tự, thao tác đầu/cuối, mutability hoặc serialization không?
5. Có thể thực hiện thay đổi theo từng module mà vẫn giữ tương thích giữa các module trong giai đoạn chuyển tiếp không?

Nếu chọn API JDK:

~~~java
import java.util.SequencedCollection;

public class OrderedCatalog {
    private SequencedCollection<String> entries;
}
~~~

Nếu chọn kiểu nội bộ:

~~~java
import com.company.collections.SequencedCollection;

public class OrderedCatalog {
    private SequencedCollection<String> entries;
}
~~~

Nếu phải sử dụng cả hai:

~~~java
public class OrderedCatalog {
    private java.util.SequencedCollection<String> platformEntries;
    private com.company.collections.SequencedCollection<String> legacyEntries;
}
~~~

Sau khi chọn, cập nhật import và chữ ký liên quan, biên dịch bằng Java 21, chạy test, kiểm tra các module tiêu thụ và xem xét API compatibility. Không chỉ đổi import rồi kết luận migration hoàn tất.

## 12. Kết quả cần có sau khi rà soát import

Đối với mỗi xung đột hoặc vùng import có rủi ro, nên ghi lại:

- File và module sở hữu source.
- Tên đơn giản bị trùng.
- Các package/kiểu cùng cung cấp tên đó.
- JDK release trước và sau migration.
- Kiểu được chọn và lý do lựa chọn.
- Thay đổi import hoặc tên đầy đủ đã thực hiện.
- Ảnh hưởng đến public API, module khác và serialization nếu có.
- Build/test đã chạy và kết quả.
- Ngoại lệ còn tồn tại, người phụ trách và điều kiện xử lý tiếp theo.

Việc kiểm kê này giúp nhóm phân biệt lỗi cú pháp import với thay đổi API thực sự. Một lỗi ambiguous reference có thể chỉ cần import tường minh, nhưng việc thay kiểu từ thư viện sang API JDK có thể là một quyết định tương thích lớn hơn. Cần lưu lại lý do để lần nâng cấp tiếp theo không phải điều tra lại từ đầu.
