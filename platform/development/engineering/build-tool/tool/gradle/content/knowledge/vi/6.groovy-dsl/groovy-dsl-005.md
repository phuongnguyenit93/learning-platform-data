# Groovy DSL: Truy cập thuộc tính, gọi phương thức và các dạng cú pháp rút gọn

## Mục tiêu bài học

Khi đọc **build.gradle** hay **settings.gradle**, ta thường gặp **version = '1.0'**, **id 'java'**, **implementation 'g:m:v'** và **repositories { mavenCentral() }**. Những câu này kết hợp cú pháp của **ngôn ngữ Groovy** với các phương thức, thuộc tính và quy ước do **Gradle API** cung cấp. Hiểu được sự kết hợp đó sẽ giúp bạn đọc script, đoán đúng đối tượng đang được cấu hình và xử lý lỗi nhanh hơn.

Sau bài học, bạn có thể:

1. Phân biệt **truy cập property**, **gọi phương thức** và **truy cập field**.
2. Hiểu quan hệ giữa **obj.name**, **getName()**, **setName(...)** và **obj.name = ...**.
3. Đọc đúng **Map**, **named arguments**, **closure** và các block cấu hình Gradle.
4. Dùng hợp lý cú pháp bỏ ngoặc, bỏ chấm phẩy, bỏ return, **GString**, **?.**, **?:**, **[]**, ***.** và tham số ngầm **it**.
5. Xác định object đích trong nested closures, biết sự khác nhau giữa code cấu hình project với **task action**.
6. Biến một dòng Groovy DSL ngắn thành câu gọi API tường minh khi cần tìm nguyên nhân lỗi.

Bài này nói về **Groovy DSL** (file **.gradle**). File **.gradle.kts** sử dụng **Kotlin DSL**: dù Gradle API có liên quan, cú pháp ngôn ngữ không thể trao đổi bằng cách đổi đuôi file.

## 1. Nhìn một build.gradle dưới góc độ Groovy

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.16'
}
~~~

Có thể đọc theo các thao tác:

- **plugins { ... }** là một block đặc biệt của Gradle. **id 'java-library'** có dạng lời gọi phương thức với một đối số và không ghi dấu ngoặc.
- **group = ...**, **version = ...** là phép **gán thuộc tính** của Project tại cấp build script này.
- **repositories { ... }** là cách gọi method nhận một **closure** để cấu hình nơi tìm dependency.
- **mavenCentral()** là lời gọi **method không có đối số** trong đối tượng cấu hình repository.
- **dependencies { ... }** là closure cấu hình dependency.
- **implementation '...'** thêm dependency vào configuration **implementation** khi plugin tương ứng đã tạo configuration này.

Phiên bản thư viện ở đây chỉ là ví dụ cú pháp, không phải gợi ý cập nhật.

| Thành phần | Groovy chịu trách nhiệm | Gradle chịu trách nhiệm |
| --- | --- | --- |
| **version = '1.0'** | Cú pháp gán property | Project có property **version** |
| **id 'java'** | Cách gọi có thể bỏ ngoặc | Plugins DSL xử lý yêu cầu plugin **java** |
| **repositories { }** | Truyền closure | Cấu hình repository handler |
| **implementation 'g:m:v'** | Gọi method dạng ngắn | Thêm dependency vào configuration đã tồn tại |

**Nguyên tắc:** Groovy quyết định một câu **được viết như thế nào**; Gradle/plugin quyết định **câu ấy thao tác lên đối tượng gì và có được phép hay không**.

## 2. Property: dấu chấm, getter và setter

### 2.1. Property Groovy thường

Một object có property **name** thường hỗ trợ đọc bằng **object.name** và gán bằng **object.name = value**. Đối với property theo quy ước JavaBeans, cách đọc/ghi tương ứng với **getName()** và **setName(value)**.

Ví dụ **Groovy độc lập**, file **PersonDemo.groovy**:

~~~groovy
class Person {
    String name
}

def person = new Person(name: 'Lan')

println person.name
println person.getName()

person.name = 'Minh'
println person.getName()
~~~

Đầu ra:

~~~text
Lan
Lan
Minh
~~~

Giải thích:

- **String name** trong lớp Groovy tạo property thông thường với getter/setter.
- **new Person(name: 'Lan')** sử dụng cách khởi tạo theo tên property mà lớp Groovy phù hợp có thể hỗ trợ.
- **person.name** là cách đọc property ngắn; **person.getName()** gọi getter tường minh.
- **person.name = 'Minh'** gán property, cho kết quả phù hợp khi đọc lại.

**Không hiểu object.name là luôn đọc field vật lý**: getter có thể tính toán kết quả hoặc áp dụng logic. Groovy có toán tử **object.@name** để truy cập field trực tiếp, nếu field tồn tại và có thể truy cập. Dạng **.@** chủ yếu dùng trong mã chuyên biệt, không phải cách thông thường để đọc property Gradle.

### 2.2. Property của Gradle Project

Trong **build.gradle**:

~~~groovy
version = '1.2.0'
println project.version
~~~

Ở cấp script project, **version** là property của Project. Dạng API tường minh:

~~~groovy
project.setVersion('1.2.0')
println project.getVersion()
~~~

Cả hai cách thể hiện cùng ý định gán và đọc version trong ví dụ.

| Property | Ý nghĩa thường gặp |
| --- | --- |
| **project.name** | Tên Project |
| **project.path** | Đường dẫn project, ví dụ **:app** |
| **project.version** | Version của Project |
| **project.group** | Group của Project |
| **project.description** | Mô tả Project |
| **project.projectDir** | Thư mục vật lý của Project |
| **task.name** | Tên của Task khi biến **task** thực sự tham chiếu một Task |

**Cẩn thận:** có thể tồn tại property trùng tên trên các object khác nhau. Ví dụ **Project.group** dùng cho metadata, **Task.group** dùng phân loại task. Dấu chấm giúp xác định đúng object.

### 2.3. Biến cục bộ và property Gradle khác nhau

~~~groovy
def label = 'demo'                // Biến Groovy
ext.releaseChannel = 'dev'       // Extra property của Project

println label
println project.ext.releaseChannel
~~~

- **def** khai báo biến trong phạm vi Groovy phù hợp.
- **ext.releaseChannel** tạo/thay đổi extra property thông qua cơ chế Gradle.
- **project.findProperty('releaseChannel')** tìm property theo cơ chế Project; không tự động đọc một biến **def** trùng tên.
- Không gán một tên tùy ý ở mọi chỗ rồi cho rằng Gradle sẽ tự tạo property.

Với giá trị cấu hình từ **gradle.properties**, Gradle có Provider API:

~~~groovy
def labelProvider = providers.gradleProperty('courseLabel')
~~~

Khi cần giá trị mặc định, có thể dùng **labelProvider.getOrElse('Gradle')**. Không gọi **get()** quá sớm nếu build cần giữ lazy configuration.

## 3. Map: dấu chấm có thể đọc key

Groovy hỗ trợ Map literal và cú pháp truy cập key gọn:

~~~groovy
def options = [host: 'localhost', port: 8080, enabled: true]

println options.host
println options['port']
println options.missing
~~~

Đầu ra:

~~~text
localhost
8080
null
~~~

- **options.host** đọc entry có key **host**.
- **options['port']** đọc entry bằng chỉ số.
- **options.missing** trả null khi Map không có entry đó; object Groovy khác có thể ném **MissingPropertyException** nếu không tồn tại property.

Một cạm bẫy là key trùng tên method:

~~~groovy
def config = [size: 99, module: 'api']

assert config.size == 99
assert config.size() == 2
assert config['module'] == 'api'
~~~

**config.size** đọc key **size**; **config.size()** gọi method của Map, trả về **2** entry. Đối với key như **size** hoặc **class**, viết **config['size']** / **config.get('size')** để tránh nhầm lẫn.

Nhiều DSL plugin nhận Map tùy chọn, nhưng cũng có block cấu hình object cụ thể. Không suy ra mọi dấu chấm bên trong Gradle đều là Map lookup.

## 4. Gọi phương thức với ngoặc

Lời gọi tường minh trong Groovy:

~~~groovy
println('Xin chào')
def highest = Math.max(4, 9)
def upper = 'gradle'.toUpperCase()
~~~

- **obj.method(a, b)** gọi method trên object.
- **method(a)** gọi method có thể được giải quyết trong phạm vi hiện tại.
- **method()** là lời gọi rõ ràng cho method **không có đối số**.
- Method có thể có nhiều overload; chữ ký thực tế (số/kiểu đối số) vẫn quan trọng.

Ví dụ Groovy độc lập:

~~~groovy
String greeting(String who) {
    "Hello, ${who}!"
}

println greeting('An')
println Math.max(4, 9)
~~~

Đầu ra:

~~~text
Hello, An!
9
~~~

Ở đây method **greeting** trả về kết quả của biểu thức cuối, vì Groovy cho phép **implicit return**. Viết **return** tường minh cũng hợp lệ.

## 5. Bỏ ngoặc khi gọi method: command expressions

Groovy có thể bỏ **(...)** trong nhiều method call có đối số, khi câu không mơ hồ:

~~~groovy
println('Hi')
println 'Hi'
~~~

Hai dòng cùng in **Hi**.

Một ví dụ khác:

~~~groovy
def a = Math.max(4, 9)
def b = Math.max 4, 9

assert a == 9
assert b == 9
~~~

Trong Gradle, khả năng này dẫn đến cú pháp ngắn:

| Viết tường minh | Viết ngắn | Điều cần nhớ |
| --- | --- | --- |
| **println('Ready')** | **println 'Ready'** | Dạng Groovy có một đối số |
| **id('java')** | **id 'java'** | Theo quy tắc riêng của **plugins { }** |
| **implementation('g:m:v')** | **implementation 'g:m:v'** | Configuration cần tồn tại |
| **from('src')** | **from 'src'** | Đối tượng hiện tại phải có method **from** |
| **mavenCentral()** | **không xóa ngoặc** | Method không có tham số |
| **project.getVersion()** | **project.version** | Đây là **cú pháp property**, không chỉ là bỏ ngoặc |

**Phương thức không đối số:** nếu bạn viết **mavenCentral** thay cho **mavenCentral()**, Groovy có thể coi đó là biến/property thay vì thực hiện lời gọi method. Hãy giữ **()** khi method không có đối số.

**Biểu thức lồng nhau:** với nhiều method, toán tử hoặc cách ghép lời gọi, lược bỏ ngoặc có thể làm cách phân tích câu trở nên mơ hồ. Khi debug, trở về **object.method(arg1, arg2)**. Groovy còn hỗ trợ **command chains** phức tạp; điều đó không có nghĩa ta cần viết Gradle script theo cách khó đọc.

Ví dụ giữ ngoặc để rõ thứ tự:

~~~groovy
println(Math.max(4, 9))
println(config.size())
~~~

## 6. Named arguments thường là Map

Cách gọi sau trông như truyền tham số theo tên:

~~~groovy
def describe(Map settings) {
    "${settings.language}/${settings.level}"
}

println describe(language: 'groovy', level: 'basic')
println describe([language: 'groovy', level: 'basic'])
~~~

Đầu ra:

~~~text
groovy/basic
groovy/basic
~~~

Trong ví dụ, cả hai lần gọi đều truyền Map cho method **describe**.

Phân biệt:

1. **[language: 'groovy', level: 'basic']** là Map literal.
2. **describe(language: 'groovy', level: 'basic')** là cách gọi **named arguments** của Groovy; thường được chuyển thành **Map làm đối số đầu tiên**.
3. Đây không phải tính năng cho phép gọi mọi Java method theo tên tham số như Kotlin. Method phải có chữ ký hoặc cách xử lý Map phù hợp.
4. **new Person(name: 'Lan')** là cách khởi tạo property của những lớp Groovy phù hợp, không chứng minh rằng mọi constructor Java đều nhận named arguments.
5. Khi đọc Gradle/plugin DSL, cần xem tài liệu method cụ thể để biết nó nhận **Map**, **Closure**, **Action** hay những đối số khác.

Named arguments và closure đều có thể làm cấu hình ngắn gọn, nhưng chúng là **hai cơ chế khác nhau**.

## 7. Closure: đối số là một khối mã

**Closure** là khối mã Groovy có thể được truyền cho method và gọi khi cần:

~~~groovy
def doubleValue = { int x ->
    x * 2
}

println doubleValue(5)
~~~

Đầu ra:

~~~text
10
~~~

### 7.1. Truyền closure ở cuối lời gọi

Hai cách viết cùng ý nghĩa:

~~~groovy
def a = [1, 2, 3].collect({ number ->
    number * 2
})

def b = [1, 2, 3].collect { number ->
    number * 2
}

assert a == b
assert b == [2, 4, 6]
~~~

Groovy cho phép đặt closure cuối ở ngoài dấu ngoặc, nên cấu hình Gradle thường có dạng **method { ... }**.

### 7.2. it là tham số ngầm

~~~groovy
def doubled = [1, 2, 3].collect { it * 2 }
println doubled
~~~

Đầu ra:

~~~text
[2, 4, 6]
~~~

**{ it * 2 }** có vai trò tương tự **{ number -> number * 2 }** trong ví dụ. Dùng **it** cho closure ngắn, nhưng nên khai báo tên **{ item -> ... }** khi closure dài hoặc lồng nhau để không nhầm **it** của từng cấp.

### 7.3. this, owner, delegate và Gradle DSL

Closure có một số thành phần ảnh hưởng cách phân giải tên:

- **this**: đối tượng theo ngữ cảnh lexical nơi closure được định nghĩa.
- **owner**: object hoặc closure chứa nơi khai báo closure.
- **delegate**: object mà closure có thể dùng để tìm method/property.
- **resolveStrategy**: quy tắc ưu tiên giải quyết tên qua owner hay delegate khi phù hợp.

Gradle sử dụng closure để cấu hình object đích:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Block **repositories** cấu hình đối tượng **RepositoryHandler**; bên trong, **mavenCentral()** là method trên object thích hợp nên không cần nêu lại object ở mỗi dòng.

Tương tự:

~~~groovy
tasks.register('sayHello') {
    group = 'help'
    description = 'Ví dụ cấu hình task'
    doLast {
        println 'Hello'
    }
}
~~~

**group** và **description** trong block task thuộc **Task** được cấu hình, không phải mặc định thuộc Project. Tuy nhiên không phải closure nào cũng có cùng delegate. **collect { }**, **repositories { }** và **doLast { }** không được giả định có cùng ngữ cảnh.

### 7.4. Closure cấu hình và action chạy khác thời điểm

~~~groovy
println 'Configuring'

tasks.register('hello') {
    doLast {
        println 'Executing'
    }
}
~~~

- Dòng **Configuring** ở top-level chạy khi project được cấu hình.
- Closure truyền cho **tasks.register** cấu hình task theo cơ chế đăng ký/hiện thực hóa lazy.
- Closure truyền cho **doLast** là **task action**, được chạy trong giai đoạn execution nếu task thực sự chạy.

Đừng hiểu mọi dấu **{ ... }** trong Gradle là khối thực thi ngay tại thời điểm dòng xuất hiện. Cần xem API nào nhận closure và **vòng đời Gradle**.

## 8. Ví dụ build.gradle chạy được

Ví dụ sau chỉ cần Gradle Wrapper hợp lệ của một dự án thực hành; không yêu cầu thư viện ngoài.

**settings.gradle**:

~~~groovy
rootProject.name = 'groovy-dsl-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'base'
}

group = 'com.example'
version = '1.0.0'

tasks.register('showDsl') {
    group = 'help'
    description = 'Minh họa Groovy DSL'

    doLast {
        println "Project group: ${project.group}"
        println "Project version: ${project.version}"
        println "Task name: ${name}"
    }
}
~~~

Từ thư mục root đã có Wrapper, chạy:

~~~bash
# Linux/macOS
./gradlew showDsl
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat showDsl
~~~

Các dòng do **task action** in ra:

~~~text
Project group: com.example
Project version: 1.0.0
Task name: showDsl
~~~

Gradle còn có dòng tên task, thông báo trạng thái và log khác; ba dòng trên chỉ là stdout do code ví dụ tự in.

Đọc script theo cách tường minh:

1. **plugins { id 'base' }**: block plugin và cách gọi **id** không ngoặc.
2. **group = 'com.example'**: thuộc tính **Project.group**.
3. **version = '1.0.0'**: thuộc tính **Project.version**.
4. **tasks.register('showDsl')**: gọi method **register** trên **TaskContainer**.
5. Closure sau **register** cấu hình Task, nên **group = 'help'** là **Task.group**.
6. **doLast { ... }** thêm action chạy khi task thực thi.
7. **println "Project group: ${project.group}"**: lời gọi **println** dạng ngắn, truyền GString chứa biểu thức property.

Khi tên **name** hoặc **group** có thể gây nhầm, có thể đặt tham số closure:

~~~groovy
tasks.register('showName') { task ->
    task.doLast {
        println "Task name: ${task.name}"
    }
}
~~~

Lúc này **task.name** nêu rõ object đích, không cần dựa vào cách resolve tên trần trong nested closure.

### 8.1. Cách đọc dependencies

~~~groovy
plugins {
    id 'java-library'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.16'
}
~~~

Lời gọi cuối có thể trình bày tường minh:

~~~groovy
dependencies {
    implementation('org.slf4j:slf4j-api:2.0.16')
}
~~~

Hai dạng có cùng mục đích trong ngữ cảnh DependencyHandler có configuration **implementation**. **implementation** không phải lời gọi Groovy có sẵn ở mọi đối tượng; plugin như **java-library** cung cấp configuration này. **mavenCentral()** phải được gọi trong vùng repositories phù hợp và giữ ngoặc vì không có đối số.

### 8.2. plugins block có quy tắc đặc thù

~~~groovy
plugins {
    id 'java'
}
~~~

**plugins { ... }** là block đặc biệt của Gradle với các ràng buộc về cú pháp và plugin request. Khả năng gọi phương thức động của Groovy không cho phép viết tùy ý mọi biểu thức bên trong block này. Khi cần logic chọn plugin phức tạp, xem **pluginManagement**, convention plugins và tài liệu Gradle tương ứng.

## 9. Các cú pháp Groovy ngắn khác nên biết

### 9.1. Bỏ dấu chấm phẩy cuối dòng

~~~groovy
def a = 2
def b = 3
println a + b
~~~

Đầu ra:

~~~text
5
~~~

Dấu **;** thường không cần nếu mỗi dòng một câu lệnh. Nếu viết nhiều câu cùng dòng, cần dấu phân cách:

~~~groovy
def a = 2; def b = 3; println a + b
~~~

Thực tế nên dùng mỗi dòng một ý để dễ đọc.

### 9.2. Bỏ return ở biểu thức cuối

~~~groovy
int add(int a, int b) {
    a + b
}

println add(2, 3)
~~~

Đầu ra:

~~~text
5
~~~

Biểu thức cuối của method/closure Groovy có thể là giá trị trả về. Với cấu hình Gradle, **closure** còn có semantics do API Gradle cung cấp; đừng coi mọi block cấu hình là method đang trả về một giá trị nghiệp vụ.

### 9.3. Chuỗi đơn và GString nội suy

~~~groovy
def module = 'core'

println "Module: ${module}"
println 'Module: ${module}'
~~~

Đầu ra:

~~~text
Module: core
Module: ${module}
~~~

- **'...'** là chuỗi đơn, **không nội suy**.
- **"..."** có thể nội suy **$name** hoặc **${expression}**.
- Dùng **${...}** khi cần biểu thức/property/method rõ ràng.
- Dùng chuỗi đơn cho tên plugin/dependency cố định nếu không cần nội suy.

Ví dụ:

~~~groovy
def number = 12
println "${number.toString()}"
~~~

Dạng **"${number.toString()}"** rõ ràng hơn **"$number.toString()"**, vì nội suy bằng **$name** có quy tắc riêng với dấu chấm và có thể bị hiểu là đọc property **toString**, rồi nối chuỗi **()**.

### 9.4. ?. — truy cập an toàn khi null

~~~groovy
def user = null
println user?.name
~~~

Đầu ra:

~~~text
null
~~~

**?.** không dereference đối tượng nếu bên trái null. Nó **không** làm hợp lệ một property/method thực sự không tồn tại trên object khác null.

### 9.5. ?: — Elvis, giá trị dự phòng

~~~groovy
def label = null
println label ?: 'default'
~~~

Đầu ra:

~~~text
default
~~~

Elvis dùng **Groovy Truth**. Không chỉ null, mà **false**, số **0**, chuỗi rỗng và collection rỗng cũng có thể chọn nhánh dự phòng. Khi mục tiêu chỉ là phân biệt null, nên kiểm tra rõ ràng.

Ví dụ Gradle:

~~~groovy
def label = project.findProperty('courseLabel') ?: 'Gradle'
~~~

Dòng này dùng fallback nếu property không có hoặc là giá trị false-like. Đừng dùng cách này để im lặng che mất cấu hình bắt buộc.

### 9.6. [] — List và Map

~~~groovy
def modules = ['app', 'core']
def config = [mode: 'debug']

println modules[0]
println config['mode']
~~~

Đầu ra:

~~~text
app
debug
~~~

Dấu **[]** là cú pháp chỉ số, có semantics tùy loại object. Không đồng nhất nó với property access cho mọi trường hợp.

### 9.7. *. — spread-dot

~~~groovy
def modules = [[name: 'app'], [name: 'core']]
println modules*.name
~~~

Đầu ra:

~~~text
[app, core]
~~~

Spread-dot lấy property trên từng phần tử. Nó hữu ích với collection Groovy; không nên dùng để suy luận cơ chế lazy của **TaskProvider** hay **Provider** trong Gradle.

### 9.8. .& — method pointer

~~~groovy
def upper = 'abc'.&toUpperCase
println upper()
~~~

Đầu ra:

~~~text
ABC
~~~

**.&** tạo method pointer/closure để gọi sau; nó khác **.@** truy cập field trực tiếp. Các dạng này ít cần trong Gradle script cơ bản nhưng có thể xuất hiện trong build logic nâng cao.

## 10. Property API của Gradle không phải property Groovy thuần

Gradle có **Provider<T>**, **Property<T>** và những đối tượng cấu hình hỗ trợ tính lazy. Ví dụ:

~~~groovy
def courseName = providers.gradleProperty('courseName')

tasks.register('showCourse') {
    doLast {
        println courseName.getOrElse('Gradle')
    }
}
~~~

Nếu property **courseName** không được cấu hình, action in **Gradle**; nếu có thì lấy giá trị tương ứng.

Một vài lưu ý:

- **Provider.get()** lấy giá trị hiện có, có thể lỗi nếu chưa có giá trị.
- **getOrElse(default)** cung cấp fallback.
- **Property.set(value)** là method API của Gradle; không phải mọi trường hợp **x = value** và **x.set(value)** đều tương đương ở mọi kiểu hoặc mọi phiên bản plugin.
- Việc gọi **get()** ngay tại configuration có thể làm mất lợi ích lazy hoặc khiến build cần giá trị sớm.
- Với credentials/token, không in giá trị ra log để “debug property”.

Đọc API của đúng object trước khi chọn cú pháp; cú pháp Groovy ngắn không thay đổi semantics của Gradle Provider.

## 11. Tránh nhầm phạm vi ở nested closures

Xem:

~~~groovy
group = 'com.example'

tasks.register('inspect') { task ->
    task.group = 'help'

    task.doLast {
        println "Project group: ${project.group}"
        println "Task group: ${task.group}"
    }
}
~~~

Hai dòng do action in ra:

~~~text
Project group: com.example
Task group: help
~~~

Cùng tên **group** nhưng thuộc hai object khác nhau. Đặt tên tham số **task ->** và dùng **task.group** làm sự khác biệt hiện rõ.

Một ví dụ khác:

~~~groovy
def label = 'outer'

tasks.register('printLabel') {
    doLast {
        println label
    }
}
~~~

**label** là biến cục bộ được closure giữ lại, không tự động trở thành Project property. Nếu cần cấu hình từ Gradle, hãy chọn API rõ ràng như **project.findProperty('label')** hoặc **providers.gradleProperty('label')**.

Khi lỗi liên quan đến scope, thử viết rõ **project.**, **task.**, **ext.** hoặc dùng biến task tường minh; không nên chỉ thay đổi dấu ngoặc ngẫu nhiên.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| **Could not get unknown property 'x'** | Property chưa tồn tại hoặc closure resolve sai object | Kiểm tra scope, object, plugin/extension; viết object tường minh |
| **Could not find method implementation()** | Chưa có configuration **implementation**, hoặc lời gọi sai block | Kiểm tra plugin Java/Java Library và **dependencies** |
| **Could not find method mavenCentral()** | Gọi trên object sai | Kiểm tra vị trí **repositories { mavenCentral() }** và policy repository của build |
| **MissingMethodException** | Method không có chữ ký tương ứng hoặc cách bỏ ngoặc làm cú pháp khó hiểu | Viết lại **object.method(args)**, xem chữ ký thật |
| **MissingPropertyException** | Property không tồn tại trên object thường | Kiểm tra getter/field và phân biệt Map key |
| Viết **mavenCentral** mà không gọi | Bỏ ngoặc method không đối số | Viết **mavenCentral()** |
| Gán nhầm **group**, **name**, **version** | Đang ở closure cấu hình object khác | Dùng **project.group** / **task.group** hoặc biến rõ |
| GString không nội suy | Dùng chuỗi đơn hoặc nhầm cách viết **${...}** | Dùng chuỗi kép và ngoặc nhọn nội suy |
| **NullPointerException** | Có object trung gian null | Kiểm tra null hoặc dùng **?.** đúng chỗ |
| Named arguments không được method chấp nhận | Method không nhận Map hoặc kiểu phù hợp | Tra API, truyền đúng kiểu |
| **plugins { }** từ chối biểu thức | Block plugins có cú pháp riêng | Theo tài liệu plugins DSL và pluginManagement |
| **println** chạy lúc cấu hình, không phải khi task chạy | Code ở top-level thay vì trong task action | Di chuyển hành vi chủ đích vào **doLast { ... }** |
| Script Groovy sao chép sang **.gradle.kts** lỗi | Groovy DSL và Kotlin DSL dùng ngôn ngữ khác | Viết lại theo cú pháp Kotlin, không chỉ đổi phần mở rộng |

**Cách debug:** đọc vị trí lỗi → nhận diện object đang được cấu hình → viết dạng tường minh **object.property** / **object.method(args)** → kiểm tra method/property do plugin nào cung cấp → chỉ rút gọn lại sau khi đã hiểu.

## 13. Bài tập tự kiểm tra

### Bài 1: Nhận diện lời gọi rút gọn

~~~groovy
println 'Learning Gradle'
def items = ['a', 'b']
println items.size()
~~~

**Đáp án:** **println 'Learning Gradle'** tương đương **println('Learning Gradle')**; **items.size()** giữ ngoặc vì **size** không nhận đối số.

### Bài 2: Đọc Map

~~~groovy
def data = [name: 'An', age: 20]
println data.name
println data['age']
println data.missing
~~~

Đầu ra:

~~~text
An
20
null
~~~

**Vì sao?** **data** là Map, phép truy cập property-like đọc key.

### Bài 3: Đọc hai group khác nhau

~~~groovy
group = 'com.example'
tasks.register('verify') {
    group = 'verification'
    doLast {
        println project.group
    }
}
~~~

**Đáp án:** in **com.example**. Group trong closure cấu hình task là **Task.group**; **project.group** vẫn giữ group cấp Project.

### Bài 4: Phân biệt configuration và execution

~~~groovy
println 'Configuring'
tasks.register('hello') {
    doLast { println 'Executing' }
}
~~~

**Đáp án:** **Configuring** chạy trong giai đoạn cấu hình Project; **Executing** chạy khi task **hello** được thực thi.

### Bài 5: Làm rõ object cho closure

Từ:

~~~groovy
tasks.register('greet') {
    doLast { println 'Hello' }
}
~~~

Viết rõ hơn:

~~~groovy
tasks.register('greet') { task ->
    task.doLast {
        println('Hello')
    }
}
~~~

Hai cách thể hiện cùng ý định đăng ký task in **Hello**; cách thứ hai giúp thấy **task** là object nhận method **doLast**.

### Bài 6: Vì sao gọi implementation có thể lỗi?

~~~groovy
dependencies {
    implementation 'org.example:demo:1.0'
}
~~~

**Đáp án:** nếu module không áp dụng plugin tạo configuration **implementation**, lời gọi DSL tương ứng có thể không tồn tại. Hãy kiểm tra **plugins**, configuration và chữ ký API trước khi kết luận rằng lỗi do dấu ngoặc.

## 14. Checklist cuối bài

- **obj.name**: đọc property hay key Map? Ai sở hữu object đó?
- **obj.name = value**: property có setter/cơ chế gán nào?
- **f 'x'**: method nào đang được gọi? Dạng **f('x')** có hợp lệ?
- **f()**: method không đối số; không tự ý bỏ **()**.
- **f(key: value)**: method có nhận Map/named args không?
- **f { ... }**: closure là đối số; delegate và giai đoạn chạy là gì?
- **${...}**: nội suy GString với chuỗi kép; chuỗi đơn không nội suy.
- **?.**, **?:**, **[]**, ***.**: nhớ đúng semantics và kiểu dữ liệu.
- **Property/Provider Gradle**: theo API, xét tính lazy, tránh gọi **get()** sớm.
- Khi không chắc, **viết tường minh** rồi mới chọn cú pháp rút gọn để dễ đọc.

## Nguồn tham khảo chính thức

- [Gradle — A Groovy Build Script Primer](https://docs.gradle.org/current/userguide/groovy_build_script_primer.html): property và method trong Gradle Groovy DSL.
- [Gradle — Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts_intermediate.html): closure và delegate của Gradle.
- [Gradle — Groovy DSL Reference](https://docs.gradle.org/current/dsl/): method/property và cấu trúc build script.
- [Apache Groovy — Language Semantics](https://www.groovy-lang.org/semantics.html): optional parentheses, semicolons và return.
- [Apache Groovy — Operators](https://docs.groovy-lang.org/latest/html/documentation/core-operators.html): safe navigation, field, spread-dot và method pointer.
- [Apache Groovy — Domain-Specific Languages](https://www.groovy-lang.org/dsls.html): command expression/chain.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): đăng ký và cấu hình task theo cách lazy.

**Ghi nhớ:** khi đọc một dòng Gradle Groovy DSL, hãy lần lượt hỏi **đối tượng nào**, **property hay method nào**, **truyền đối số/closure nào**, và **thực thi vào lúc nào**. Trả lời bốn câu hỏi đó là cách biến cú pháp rút gọn thành kiến thức Gradle rõ ràng, kiểm chứng được.