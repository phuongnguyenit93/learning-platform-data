# Phân biệt set, convention và giá trị được suy ra

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Provider và cấu hình lười

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Property<T>** (có thể cấu hình) với **Provider<T>** (nguồn giá trị chỉ để đọc), cũng như giá trị mặc định và giá trị được gán tường minh.
2. Dự đoán kết quả khi dùng **convention(value/provider)**, **set(value/provider)**, **unset()** và **Provider.orElse(...)** theo đúng thứ tự ưu tiên.
3. Tạo **giá trị được suy ra (derived value)** từ nguồn khác qua **map**, **flatMap**, **zip**, rồi gắn nguồn ấy vào Property thay vì lấy giá trị sớm.
4. Nhận diện trạng thái **có giá trị**, **không có giá trị** và các thời điểm giá trị bị **finalize**.
5. Cấu hình một custom task bằng **Property<String>** và **@Input**, chạy các lệnh Gradle để kiểm chứng giá trị mặc định, override, fallback và propagation.
6. Tránh lỗi phổ biến khi cấu hình plugin/task: gọi get() quá sớm, nghĩ convention ghi đè set, nhầm Provider với Property hoặc tự cắt đứt quan hệ phụ thuộc task.

**Ý chính:** **convention** thiết lập *mặc định*; **set** thiết lập *giá trị tường minh* (có thể lấy từ một Provider); còn **giá trị được suy ra** là Provider tạo bởi phép biến đổi hoặc kết hợp những nguồn khác. Giá trị suy ra **không tự động thắng** convention hay set: thắng hay thua phụ thuộc bạn nối Provider ấy bằng **set(...)**, **convention(...)** hay **orElse(...)**.

## 1. Đầu tiên phải hiểu Property và Provider

Gradle có mô hình Provider API để mô tả **nguồn dữ liệu**, **quan hệ biến đổi** và **thời điểm tiêu thụ giá trị**. Nó hỗ trợ lazy configuration: build có thể nối các cấu hình trước khi phải truy vấn giá trị thật.

| Khái niệm | Kiểu điển hình | Có thể thay đổi nguồn/giá trị? | Dùng để làm gì? |
|---|---|---|---|
| **Provider<T>** | Provider<String> | Người nhận không gọi set trên Provider | Đọc giá trị từ một nguồn, biến đổi hoặc kết hợp các Provider |
| **Property<T>** | Property<String> | Có thể set, convention và quản lý vòng đời | Thuộc tính đầu vào của extension/task, giữ giá trị tường minh hoặc mặc định |
| **Property cụ thể cho file** | RegularFileProperty, DirectoryProperty | Có | Dẫn đường tới file/thư mục, đồng thời hỗ trợ nối lazy với output của task |
| **Property collection** | ListProperty<T>, SetProperty<T>, MapProperty<K,V> | Có; còn có add/put thích hợp | Lưu cấu hình tập hợp với cơ chế đóng góp giá trị theo phần tử |

**Property<T> mở rộng Provider<T>.** Vì vậy một Property có thể dùng ở nơi cần Provider, nhưng một Provider thuần không có phương thức set để người dùng tùy ý thay đổi nó.

Ví dụ Groovy DSL trong build.gradle:

~~~groovy
def language = objects.property(String)
language.convention('Java')

def derived = language.map { value -> value + ' 17' }

tasks.register('showLanguage') {
    inputs.property('language', language)

    doLast {
        println 'language=' + language.get()
        println 'derived=' + derived.get()
    }
}
~~~

Nếu chỉ có đoạn này và không có cấu hình khác thay language, các dòng do action in là:

~~~text
language=Java
derived=Java 17
~~~

**Cơ chế:** objects.property(String) tạo Property<String> chưa có giá trị; convention('Java') cấp mặc định; map tạo một **Provider<String> mới**; khi task đọc derived.get(), Provider tính dựa trên giá trị language hiện tại theo vòng đời Gradle.

Đây là ví dụ ngắn để nhìn mô hình; khi viết task/plugin nghiêm túc, hãy nối cả giá trị suy ra vào Property có annotation @Input của task, thay vì chụp các biến của script trong doLast. Ví dụ đầy đủ ở mục 6 dùng task type như vậy.

### 1.1. Giá trị được suy ra không phải bản copy cố định

Xem hai cách:

~~~groovy
def version = objects.property(String)
version.convention('1.0')

def lazyTag = version.map { value -> 'v' + value }
def eagerTag = 'v' + version.get()
~~~

- lazyTag là **Provider** nối với version. Khi đọc trong thời điểm hợp lệ, Gradle truy vấn phiên bản từ nguồn hiện tại.
- eagerTag là **String** đã tính ngay tại dòng khai báo; nếu sau đó version được cấu hình bằng một giá trị khác, eagerTag không tự cập nhật.
- Lệnh get() tại configuration phase có thể lấy giá trị quá sớm, làm giảm tính linh hoạt và ảnh hưởng configuration cache/quan hệ phụ thuộc task.

**Không suy luận rằng Provider luôn được tính lại vô hạn:** Gradle có quy tắc truy vấn, kiểm tra input và finalization theo vòng đời build. Điều cần nhớ là **đường nối nguồn còn tồn tại** cho đến khi giá trị được chốt, và code của bạn không tự biến nó thành String tĩnh giữa lúc cấu hình.

## 2. convention: đặt giá trị mặc định có thể được ghi đè

convention(value) hoặc convention(provider) là cách nói:

> Nếu chưa có giá trị tường minh cho Property này thì sử dụng nguồn mặc định đã khai báo.

~~~groovy
def greeting = objects.property(String)
greeting.convention('Xin chào')
~~~

Trong trạng thái chưa có set(...), greeting.get() trả **Xin chào**.

Nếu plugin đặt convention trước, người sử dụng plugin có thể cấu hình riêng bằng set:

~~~groovy
greeting.set('Chào bạn')
~~~

Lúc này greeting.get() trả **Chào bạn**.

**Quan trọng:** convention không phải mệnh lệnh “luôn dùng giá trị này”. Nó thiết kế cho plugin **đặt default** và để người sử dụng **override**. Vì thế, plugin cần viết:

~~~groovy
// Trong logic plugin hoặc cấu hình dùng chung:
greeting.convention('Xin chào')
~~~

Sau đó build script của người dùng có thể ghi:

~~~groovy
// Trong cấu hình cụ thể:
greeting.set('Chào đội Java')
~~~

Khi dữ liệu không nhạy cảm và không có yêu cầu override, cả hai cách có thể tạo ra một giá trị ban đầu như nhau; nhưng **ý nghĩa API và quyền cấu hình của người dùng khác nhau**.

### 2.1. Convention có thể đến từ Provider

~~~groovy
def fallbackName = providers.gradleProperty('appName')
    .orElse('Gradle')

def displayName = objects.property(String)
displayName.convention(fallbackName)
~~~

- providers.gradleProperty('appName') đọc một **project property** từ những nguồn chuẩn của Gradle.
- orElse('Gradle') cấp fallback nếu nguồn project property không có giá trị.
- displayName.convention(fallbackName) dùng Provider đó làm **default**, chứ chưa gán tường minh.
- Nếu project property appName được cung cấp, default hiển thị tên ấy, trừ khi displayName bị set riêng.

Khi dùng -PappName=Demo, Provider của appName có thể mang giá trị Demo; nhưng nếu build script gọi displayName.set('Tên khác'), **Tên khác** vẫn thắng vì đó là giá trị tường minh của displayName.

### 2.2. Convention khác Provider.orElse

Hai dòng sau thuộc **hai cấp cấu hình khác nhau**:

~~~groovy
displayName.convention('Mặc định từ Property')

def effectiveName = providers.gradleProperty('appName')
    .orElse('Fallback của Provider')
~~~

- convention(...) gắn giá trị mặc định cho một **Property có thể thay đổi**.
- orElse(...) tạo Provider có fallback khi **Provider nguồn không có giá trị**. Nó không sửa source và không tạo một “mặc định chung” cho mọi Property.
- Khi dùng displayName.set(effectiveName), Provider có fallback được dùng làm **giá trị tường minh** của displayName, vì được truyền vào set.
- Khi dùng displayName.convention(effectiveName), Provider có fallback trở thành **mặc định** của displayName.

Vì vậy, hai biểu thức cùng chứa chữ “mặc định” nhưng không thể coi là hoàn toàn tương đương.

## 3. set: thiết lập giá trị tường minh và thay nguồn hiện có

### 3.1. set với giá trị cụ thể

~~~groovy
def label = objects.property(String)
label.convention('Mặc định')
label.set('Tường minh')
~~~

Kết quả label.get() là **Tường minh**. set(value) thay giá trị tường minh trước đó và được ưu tiên hơn convention.

Bạn có thể set nhiều lần **khi Property vẫn được phép cấu hình**:

~~~groovy
label.set('A')
label.set('B')
~~~

Nếu chưa finalize, giá trị cuối được gán là **B**. Tuy nhiên, một build tốt nên cấu hình một cách có chủ đích; không nên rải nhiều set ở các plugin, subproject và task rồi dựa vào thứ tự tình cờ.

### 3.2. set với Provider: rõ ràng nhất để giữ tính lazy

~~~groovy
def base = objects.property(String)
base.convention('service')

def source = base.map { value -> value + '-api' }

def result = objects.property(String)
result.convention('backup')
result.set(source)
~~~

result.get() nhận **service-api**. Ở đây set(source) không lập tức biến Provider thành String; Property kết nối với Provider làm nguồn tường minh. Nếu base được cấu hình trước khi Gradle chốt giá trị result, nguồn suy ra có thể phản ánh cấu hình mới.

**Lợi ích:** Không phải gọi source.get() trong configuration phase. Gradle giữ được thông tin nguồn, và có thể chuyển tiếp quan hệ phụ thuộc task khi Provider là output của một task được khai báo đúng.

### 3.3. Bảng hành vi cốt lõi

Giả sử p là Property<String> mới tạo. Mỗi dòng trong bảng biểu diễn **một kịch bản độc lập**:

| Cấu hình | Giá trị hiệu lực khi truy vấn | Vì sao? |
|---|---|---|
| Không set, không convention | **Không có giá trị** | Property chưa được cấu hình |
| p.convention('A') | A | Có default |
| p.convention('A'); p.set('B') | B | set thắng convention |
| p.set('B'); p.convention('A') | B | convention mới không ghi đè giá trị tường minh |
| p.set('B'); p.set('C') | C | set sau thay giá trị tường minh trước |
| p.convention('A'); p.set(providerOfB) | B nếu provider có B | Provider của set là nguồn tường minh |
| p.convention('A'); p.set(providerWithoutValue) | **Không có giá trị** | Explicit Provider không có giá trị vẫn che convention |
| p.convention('A'); p.set('B'); p.unset() | A | unset bỏ giá trị tường minh để dùng convention |
| p.convention('A'); p.unsetConvention() | **Không có giá trị** nếu chưa set | Bỏ nguồn default |
| p.convention('A'); p.set('B'); p.unsetConvention() | B | B vẫn được set tường minh |

**Điểm rất dễ sai:** Khi set bằng một **Provider không có giá trị**, Gradle **không tự quay về convention**. Việc “đã set một Provider” là lựa chọn nguồn tường minh; nếu Provider ấy không present, Property cũng có thể không present.

Nếu bạn muốn **fallback** trước khi set, hãy đặt fallback ở nguồn:

~~~groovy
def fromCli = providers.gradleProperty('optionalName')
def withFallback = fromCli.orElse('Tên mặc định')

def p = objects.property(String)
p.convention('Default của Property')
p.set(withFallback)
~~~

Khi optionalName thiếu, p.get() là **Tên mặc định** do **orElse**, chứ không phải **Default của Property**. Không nên dựa vào convention để xử lý trường hợp Provider tường minh bị thiếu.

### 3.4. unset và bỏ convention

Với Gradle mới hỗ trợ API này, bạn có thể gọi:

~~~groovy
def p = objects.property(String)
p.convention('A')
p.set('B')
p.unset()  // quay về convention
~~~

Lúc đó p.get() là A. **unset()** loại bỏ lựa chọn tường minh, còn **unsetConvention()** loại bỏ default. Hai thao tác độc lập. Gradle hỗ trợ SupportsConvention.unset()/unsetConvention() từ Gradle 8.7; nếu dùng bản cũ, kiểm tra JavaDoc/Gradle version và cơ chế bỏ giá trị tương ứng (ví dụ set(null) của Property<T> khi đủ điều kiện).

**Lưu ý về null:** Property.set(null) có thể loại bỏ giá trị tường minh để convention được dùng, nhưng chữ null dễ gây nhầm với overload set(Provider) trong Groovy và không phải cách diễn đạt rõ ý nhất. Trong ví dụ Gradle hiện đại, dùng unset() giúp mục đích dễ đọc hơn.

## 4. Giá trị được suy ra (derived values) và các phép biến đổi

Một **derived Provider** là nguồn dữ liệu mới được định nghĩa bằng một hoặc nhiều nguồn trước đó. Nó không cần được ghi cố định thành String ở lúc khai báo.

### 4.1. map: biến đổi một giá trị thành giá trị thường

~~~groovy
def moduleName = providers.gradleProperty('moduleName')
    .orElse('catalog')

def artifactName = moduleName.map { name ->
    name + '-service'
}
~~~

moduleName là Provider<String>; artifactName cũng là Provider<String>. Khi moduleName có giá trị catalog, artifactName trả catalog-service. Khi truyền -PmoduleName=payment thì artifactName có thể trả payment-service.

**map** thích hợp khi hàm biến đổi nhận một T và trả về giá trị U thường: thêm tiền tố, đổi định dạng, phân tích số, tạo tên file, tính một cấu hình.

~~~groovy
def count = providers.gradleProperty('threadCount')
    .orElse('4')
    .map { text -> Integer.parseInt(text) }
~~~

Nếu threadCount=8, Provider mới chứa số nguyên 8. Nếu text không phải số hợp lệ, lỗi parse có thể xuất hiện khi Provider được đọc; map không phải bộ kiểm tra tự sửa dữ liệu. Hãy báo lỗi cấu hình có ý nghĩa khi parse fail.

### 4.2. flatMap: chọn hoặc lấy một Provider khác

Khi biến đổi không trả giá trị thường mà trả **Provider<U>**, dùng **flatMap**:

~~~groovy
def mode = objects.property(String)
mode.convention('dev')

def devUrl = providers.provider { 'http://localhost:8080' }
def prodUrl = providers.provider { 'https://example.org' }

def selectedUrl = mode.flatMap { currentMode ->
    currentMode == 'prod' ? prodUrl : devUrl
}
~~~

- Khi mode=dev, selectedUrl lấy từ devUrl.
- Khi mode được set('prod') trước lúc chốt, selectedUrl lấy từ prodUrl.
- flatMap tránh cấu trúc lồng Provider<Provider<String>> và giữ quan hệ tới nguồn được chọn.
- Ở ví dụ trên, giá trị URL là dữ liệu minh họa; không thực hiện request HTTP.

**Không dùng map để trả Provider rồi tưởng đã nhận String.** Nếu closure trả một Provider, map sẽ tạo Provider của đối tượng Provider; muốn nối trực tiếp tới giá trị do Provider kia cung cấp, hãy dùng flatMap.

### 4.3. zip: kết hợp hai nguồn

~~~groovy
def first = objects.property(String)
first.convention('Xin chào')

def second = objects.property(String)
second.convention('Gradle')

def sentence = first.zip(second) { a, b ->
    a + ', ' + b + '!'
}
~~~

Kết quả khi đọc sentence là **Xin chào, Gradle!**.

- first và second có thể có nguồn độc lập.
- sentence là Provider mới; bản thân sentence **không phải** Property có thể set.
- Nếu một đầu vào không present, kết quả kết hợp có thể không present; muốn fallback, bổ sung orElse cho nguồn thích hợp hoặc cho Provider kết quả.
- Không cần gọi first.get() hoặc second.get() để ghép chúng trong configuration phase.

### 4.4. orElse: fallback của Provider, không phải set hay convention

~~~groovy
def region = providers.gradleProperty('region')
    .orElse('local')

def message = region.map { value -> 'region=' + value }
~~~

Nếu region chưa được cung cấp, message nhận region=local. Khi chạy -Pregion=ap-southeast-1, message nhận region=ap-southeast-1. **orElse không sửa** nội dung gradle.properties và không có tác dụng lên các Property khác, trừ khi bạn kết nối Provider này vào chúng.

### 4.5. Sơ đồ đường đi của một giá trị

~~~text
gradle.properties hoặc -PprojectProperty
            |
            v
providers.gradleProperty('recipient') --orElse('Gradle')--> Provider<String>
            |                                                     |
            |                                                     v
            |                                           Property<String> recipient
            |                                            convention(Provider)
            |                                                     |
Property<String> prefix --convention('Xin chào')------------------+
            |                                                     |
            +--------------------- zip ----------------------------+
                                    |
                                    v
                              Provider<String>
                             "Xin chào, Gradle!"
                                    |
                  +-----------------+-----------------+
                  |                                   |
          task.label.convention(...)          task.label.set(...)
             default suy ra                  explicit suy ra
                  |                                   |
         người dùng có thể set                  convention khác
          giá trị tường minh                  không thắng được
~~~

Một Provider **được suy ra** không có “độ ưu tiên” độc lập. Nguồn nào thắng phụ thuộc vị trí trong mô hình cấu hình: đầu vào của zip/map/flatMap, Provider.orElse, và việc Property tiêu thụ nguồn bằng set hay convention.

## 5. Chọn set hay convention khi thiết kế plugin và task?

### 5.1. Khi bạn là người viết plugin

Plugin thường nên đặt giá trị **mặc định có thể cấu hình lại** bằng convention:

~~~groovy
abstract class PublishOptions {
    abstract Property<String> getChannel()
}

def options = extensions.create('publishOptions', PublishOptions)
options.channel.convention('preview')
~~~

Đây là ví dụ một **đoạn trong build.gradle** để hiểu mô hình (chưa có task publish thật). Người sử dụng có thể ghi:

~~~groovy
publishOptions {
    channel.set('release')
}
~~~

Nếu plugin dùng set('preview') để đặt giá trị mặc định, nó đã tạo một **giá trị tường minh** và dễ có xung đột khi plugin khác cũng set vào Property. Với hợp đồng public extension, convention thể hiện ý định cho phép ghi đè rõ ràng hơn.

### 5.2. Khi bạn là người tiêu thụ extension

Ở build script:

~~~groovy
publishOptions {
    channel.set('release')
}
~~~

Đây là một override rõ ràng, nên dùng set. Nếu giá trị phụ thuộc môi trường:

~~~groovy
publishOptions {
    channel.set(
        providers.gradleProperty('releaseChannel')
            .orElse('preview')
    )
}
~~~

Cách này nối Provider để giữ tính lazy. Người đọc thấy nguồn nào quyết định channel và fallback khi thiếu.

### 5.3. Khi cấu hình task

Một task type có đầu vào được mô tả bằng managed Property:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintChannel extends DefaultTask {
    @Input
    abstract Property<String> getChannel()

    @TaskAction
    void show() {
        println('channel=' + channel.get())
    }
}
~~~

Đây là **định nghĩa task type**, chưa đủ để chạy độc lập cho đến khi đặt nó trong một build.gradle và đăng ký task. Input property có @Input giúp Gradle nhận biết giá trị được sử dụng khi quyết định task execution/up-to-date. Nó cũng giúp Gradle thực hiện các kiểm tra giá trị bắt buộc ở thời điểm thực thi.

Khi đăng ký:

~~~groovy
tasks.register('printChannel', PrintChannel) {
    channel.convention(
        providers.gradleProperty('releaseChannel')
            .orElse('preview')
    )
}
~~~

Một người dùng có thể cấu hình channel tường minh sau đó qua named('printChannel') nếu plugin/task hợp đồng cho phép. Khi thiết kế plugin nhiều module, ưu tiên **extension cấp plugin có convention** được nối vào **input của task**, rồi cho task tiêu thụ dữ liệu đó; tránh rải set cứng vào hàng trăm task.

## 6. Thực hành hoàn chỉnh: thử mọi nhánh bằng Java 17 và Gradle Groovy DSL

Ví dụ sau là **một dự án chạy được**, gồm các task custom minh họa Provider và một ứng dụng Java 17 nhỏ để kiểm tra toolchain. Java main là ví dụ độc lập với nguồn Property của Gradle; task show* mới là nơi chứng minh quy tắc set/convention/derived value.

### 6.1. Cấu trúc dự án

~~~text
property-lab/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
~~~

Khi tạo Wrapper, sẽ có thêm gradlew, gradlew.bat và thư mục gradle/wrapper/. Nên dùng một bản Gradle tương thích với JDK/toolchain đã chọn. Ở máy chưa có Gradle Wrapper, dùng bản Gradle đã cài chạy **gradle wrapper** một lần rồi commit các tệp Wrapper vào Git. Những lần tiếp theo gọi ./gradlew trên Linux/macOS hoặc .\gradlew.bat trên Windows.

**settings.gradle**

~~~groovy
rootProject.name = 'property-lab'
~~~

**build.gradle** (một file đầy đủ, Groovy DSL):

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}

// Task type có đầu vào được Gradle quản lý.
abstract class PrintValue extends DefaultTask {
    @Input
    abstract Property<String> getValueToPrint()

    @TaskAction
    void printValue() {
        println 'value=' + valueToPrint.get()
    }
}

// Hai Property nguồn và một Provider được suy ra.
def prefix = objects.property(String)
prefix.convention('Xin chào')

def recipient = objects.property(String)
recipient.convention(
    providers.gradleProperty('recipient').orElse('Gradle')
)

def greeting = prefix.zip(recipient) { a, b ->
    a + ', ' + b + '!'
}

// Task 1: convention là một Provider suy ra.
tasks.register('showConvention', PrintValue) {
    group = 'verification'
    description = 'Giá trị mặc định được suy ra'
    valueToPrint.convention(greeting)
}

// Task 2: set một String tường minh thắng convention.
tasks.register('showExplicit', PrintValue) {
    group = 'verification'
    description = 'Giá trị tường minh thắng mặc định'
    valueToPrint.convention(greeting)
    valueToPrint.set('Được đặt bằng set')
}

// Task 3: set một Provider cũng là gán tường minh.
tasks.register('showFromProvider', PrintValue) {
    group = 'verification'
    description = 'Nguồn tường minh được suy ra từ Provider'
    valueToPrint.convention('fallback của task')
    valueToPrint.set(greeting)
}

// Task 4: default đơn giản, không có set.
tasks.register('showLiteralDefault', PrintValue) {
    group = 'verification'
    description = 'Convention bằng một String'
    valueToPrint.convention('Mặc định trực tiếp')
}

// Task run có nhờ plugin application.
tasks.named('run', JavaExec) {
    args 'Gradle'
}
~~~

**src/main/java/demo/App.java**

~~~java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Guest" : args[0];
        System.out.println("Java 17: " + name);
    }
}
~~~

### 6.2. Kiểm tra bốn cách cấu hình

Trên Linux/macOS, chạy riêng từng task để nhìn stdout chính xác:

~~~bash
./gradlew -q showLiteralDefault
./gradlew -q showConvention
./gradlew -q showExplicit
./gradlew -q showFromProvider
~~~

Trên PowerShell, thay ./gradlew bằng .\gradlew.bat:

~~~powershell
.\gradlew.bat -q showLiteralDefault
.\gradlew.bat -q showConvention
.\gradlew.bat -q showExplicit
.\gradlew.bat -q showFromProvider
~~~

Khi không có project property recipient được cấp từ CLI, môi trường hay gradle.properties, **đầu ra action của từng task** lần lượt là:

**showLiteralDefault:**

~~~text
value=Mặc định trực tiếp
~~~

**showConvention:**

~~~text
value=Xin chào, Gradle!
~~~

**showExplicit:**

~~~text
value=Được đặt bằng set
~~~

**showFromProvider:**

~~~text
value=Xin chào, Gradle!
~~~

Giải thích:

- showLiteralDefault lấy String mặc định trực tiếp.
- showConvention dùng greeting Provider như **mặc định**.
- showExplicit có cùng convention nhưng **set String** nên override.
- showFromProvider cũng có convention nhưng **set Provider**, nên lấy giá trị từ greeting dù fallback của task là một String khác.

Những dòng trên là stdout do @TaskAction tạo, không bao gồm log khác của Gradle.

### 6.3. Đổi nguồn đầu vào mà không sửa build.gradle

Chạy:

~~~bash
./gradlew -q showConvention -Precipient=Mai
./gradlew -q showExplicit -Precipient=Mai
./gradlew -q showFromProvider -Precipient=Mai
~~~

Đầu ra từng lệnh:

**showConvention:**

~~~text
value=Xin chào, Mai!
~~~

**showExplicit:**

~~~text
value=Được đặt bằng set
~~~

**showFromProvider:**

~~~text
value=Xin chào, Mai!
~~~

Bạn không cần set lại greeting bằng tay. recipient có convention lấy nguồn từ providers.gradleProperty('recipient'); khi -Precipient=Mai được Gradle nhìn thấy, giao thức Provider đổi nguồn hiệu lực và zip tạo câu mới.

Nhưng showExplicit vẫn không đổi vì **set('Được đặt bằng set')** đã chọn nguồn tường minh, mạnh hơn convention(greeting).

### 6.4. Chạy ứng dụng Java 17

Linux/macOS:

~~~bash
./gradlew -q run
~~~

PowerShell:

~~~powershell
.\gradlew.bat -q run
~~~

Đầu ra **Java main** là:

~~~text
Java 17: Gradle
~~~

Nếu Java toolchain 17 chưa được cung cấp và chưa có cơ chế auto-download được cấu hình, Gradle có thể không tìm được JDK phù hợp; đây là vấn đề môi trường chứ không liên quan set/convention.

Mã App.java **không đọc trực tiếp các Property của Gradle**. Dự án cố ý giữ Java main đơn giản để làm rõ rằng Provider/Property là mô hình cấu hình **build**, và muốn truyền sang JVM ứng dụng cần cấu hình args/systemProperty hoặc cơ chế runtime thích hợp. Lệnh run ở trên chỉ truyền 'Gradle' như đối số cố định.

### 6.5. Đọc giá trị trong pha cấu hình và pha thực thi

Trong build.gradle, mã:

~~~groovy
def early = greeting.get()
tasks.register('showEarly') {
    doLast {
        println 'early=' + early
    }
}
~~~

là ví dụ **không nên sử dụng làm thiết kế mặc định**, vì greeting.get() xảy ra **ngay khi cấu hình build script**, trước khi mọi plugin và task được hoàn tất cấu hình. Nếu sau đó có nơi set lại prefix/recipient, biến early không tự thay đổi; với task outputs được suy ra còn có thể làm mất thông tin producer dependency.

Thay vì thế, task PrintValue trong ví dụ chính nối valueToPrint.convention(greeting) hoặc valueToPrint.set(greeting). Gradle đọc giá trị khi task cần đầu vào; @Input khai báo rõ dữ liệu để kiểm tra up-to-date và caching theo quy tắc của Gradle.

## 7. Tình huống nâng cao: Provider vắng mặt và fallback thật sự

### 7.1. Một Provider không có giá trị

~~~groovy
def missing = providers.gradleProperty('optionalKey')

def p = objects.property(String)
p.convention('Default của p')
p.set(missing)
~~~

Nếu không có optionalKey trong các nguồn project property chuẩn, missing không present, và p cũng **không có giá trị** khi truy vấn. Giá trị Default của p không tự cứu được vì p đã được set bằng nguồn tường minh. Gọi p.get() có thể ném lỗi thiếu giá trị.

Để kiểm tra an toàn:

~~~groovy
println p.isPresent()
println p.getOrElse('Fallback khi đọc')
~~~

Đây là hai dòng minh họa truy vấn. Trong trường hợp thiếu giá trị, chúng lần lượt in false và Fallback khi đọc. **getOrElse** chỉ cung cấp fallback cho lần truy vấn Provider; không sửa trạng thái p, không đồng nghĩa p.convention(...).

### 7.2. Sửa bằng fallback ở nguồn hoặc bỏ explicit value

Hai lựa chọn tùy mục tiêu:

~~~groovy
def optional = providers.gradleProperty('optionalKey')

def a = objects.property(String)
a.convention('Default của a')
a.set(optional.orElse('Fallback của nguồn'))

def b = objects.property(String)
b.convention('Default của b')
b.set('Tạm thời')
b.unset()
~~~

Khi optionalKey thiếu:

- a.get() nhận **Fallback của nguồn** vì a đã set bằng Provider có orElse.
- b.get() nhận **Default của b** vì unset đã loại bỏ explicit value.

Nếu muốn giữ quy tắc “người dùng không cung cấp thì dùng convention của Property”, có thể **không gọi set** khi thiếu giá trị, hoặc thiết kế chuỗi Provider để fallback đúng tại nơi cần.

### 7.3. Một Provider bị biến đổi nhưng vẫn không có giá trị

~~~groovy
def optional = providers.gradleProperty('nonexistent')
def upper = optional.map { value ->
    value.toUpperCase(java.util.Locale.ROOT)
}
~~~

Nếu optional không present, upper cũng không present; closure trong map sẽ không tự tạo giá trị. Muốn có default:

~~~groovy
def safeUpper = optional
    .orElse('default')
    .map { value -> value.toUpperCase(java.util.Locale.ROOT) }
~~~

Khi optional thiếu, safeUpper trả **DEFAULT**. Đây là một ví dụ vì sao cần phân biệt **biến đổi** với **fallback**.

## 8. Vòng đời của Property: lúc nào có thể thay đổi?

Một Property có thể đang ở trạng thái chưa có giá trị, có convention, có explicit value/provider, hoặc đã được chốt (finalized). Khi Gradle thực thi task, một số đầu vào của task được Gradle chốt để tránh thay đổi giữa chừng.

### 8.1. finalizeValue

~~~groovy
def p = objects.property(String)
p.convention('A')
p.set('B')
p.finalizeValue()
~~~

Sau finalizeValue(), p có giá trị **B** cố định. Nếu code tiếp tục gọi p.set('C'), Gradle sẽ ném lỗi vì nguồn/giá trị không còn được phép thay đổi.

Nếu p đang lấy từ Provider, finalizeValue() sẽ **đọc Provider và chốt giá trị nhận được tại thời điểm gọi**, sau đó không tiếp tục theo dõi nguồn Provider để cập nhật p. Vì thế gọi finalize quá sớm có thể chốt một giá trị chưa đúng ý.

### 8.2. finalizeValueOnRead

~~~groovy
def p = objects.property(String)
p.convention('A')
p.finalizeValueOnRead()
~~~

Gradle đợi cho đến **lần đọc giá trị kế tiếp** rồi mới chốt. Trước lần đọc ấy, p vẫn có thể được cấu hình theo quy tắc của nó; sau lần đọc, các thay đổi tiếp theo sẽ bị từ chối.

Dùng khi muốn kết thúc cấu hình ở thời điểm tiêu thụ giá trị, thay vì chốt ngay tại thời điểm khai báo.

### 8.3. disallowChanges

~~~groovy
def base = objects.property(String)
base.convention('A')

def p = objects.property(String)
p.set(base)
p.disallowChanges()
~~~

disallowChanges() **cấm thay đổi trực tiếp nguồn/giá trị trên p** bằng những lời gọi như p.set(...). Khác với finalizeValue(), nó **không lập tức truy vấn và đóng băng** Provider hiện có; nếu base còn có thể thay đổi hợp lệ trước khi p được finalize, giá trị nguồn vẫn có thể tiếp tục được theo dõi.

Bảng so sánh:

| API | Khi nào đọc/khóa giá trị? | Khi nào dùng? |
|---|---|---|
| **set(...)** | Gán explicit value/source; chưa nhất thiết truy vấn Provider | Cho người dùng hoặc build logic đặt cấu hình rõ ràng |
| **convention(...)** | Cung cấp default khi chưa có explicit source/value | Plugin đặt giá trị khởi đầu có thể override |
| **finalizeValue()** | Truy vấn giá trị và chốt ngay | Khi cấu hình đã đầy đủ và cần cố định |
| **finalizeValueOnRead()** | Chốt ở lần đọc kế tiếp | Khi muốn trì hoãn chốt đến lúc thực sự đọc |
| **disallowChanges()** | Khóa việc thay source trực tiếp, chưa tự đọc nguồn | Sau khi wiring nguồn hoàn tất nhưng vẫn cần lazy source |
| **unset()** | Bỏ explicit source/value, cho convention được chọn | Khi muốn trở về default |
| **unsetConvention()** | Bỏ nguồn default | Khi muốn Property không còn convention |

**Không dùng finalization như cách giải quyết lỗi thiếu Provider.** Một Provider thiếu giá trị khi được chốt vẫn có thể gây lỗi. Hãy sửa nguồn, fallback và thứ tự wiring trước.

## 9. Giá trị suy ra từ output của task: giữ quan hệ phụ thuộc tự động

Provider API đặc biệt hữu ích khi **một task tạo file** và **task khác tiêu thụ file**. Nếu đầu ra được khai báo đúng, việc nối Provider có thể giúp Gradle xác định task producer cần chạy.

Đây là **mã minh họa cơ chế** đặt trong build.gradle của project đã có những loại task tương ứng. Nó không phải chương trình độc lập thay thế ví dụ đầy đủ ở mục 6.

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.TaskAction
import org.gradle.api.provider.Property

abstract class ProduceText extends DefaultTask {
    @Input
    abstract Property<String> getContent()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void produce() {
        def f = outputFile.get().asFile
        f.parentFile.mkdirs()
        f.setText(content.get() + '\n', 'UTF-8')
    }
}

abstract class ReadText extends DefaultTask {
    @InputFile
    abstract RegularFileProperty getInputFile()

    @TaskAction
    void read() {
        println inputFile.get().asFile.getText('UTF-8').trim()
    }
}

def producer = tasks.register('produceText', ProduceText) {
    content.convention('Xin chào từ task producer')
    outputFile.set(layout.buildDirectory.file('generated/message.txt'))
}

tasks.register('readText', ReadText) {
    inputFile.set(producer.flatMap { task -> task.outputFile })
}
~~~

Ý nghĩa:

- ProduceText có **@OutputFile RegularFileProperty** được khai báo trực tiếp trên managed task property.
- ReadText có **@InputFile RegularFileProperty** để Gradle theo dõi đầu vào file.
- producer là **TaskProvider<ProduceText>**, không phải task instance đã phải được tạo ngay.
- producer.flatMap { task -> task.outputFile } lấy **Provider của output file** và giữ quan hệ task producer; khi chạy readText, Gradle biết producer cần được thực thi nếu thích hợp.
- Không cần tự chèn dependsOn chỉ để nối file output này; Provider mang quan hệ phụ thuộc nhiệm vụ sản xuất dữ liệu.
- Câu lệnh content.get() và inputFile.get() chỉ xuất hiện **bên trong TaskAction**, khi thực thi; không có việc đọc output file trước khi producer tạo nó.

Chạy:

~~~bash
./gradlew -q readText
~~~

Đầu ra do task đọc tạo ra là:

~~~text
Xin chào từ task producer
~~~

**Lưu ý:** Nếu dùng một Provider rời rạc kiểu providers.provider { producer.get().outputFile.get().asFile } để tự bao task output, Gradle có thể mất dấu quan hệ task dependency. Hãy nối từ TaskProvider tới output Property có annotation bằng **flatMap**, rồi chuyển thành dữ liệu khác bằng **map** khi cần. Không lấy File rồi đọc text ngay ở cấu hình build.

## 10. Quy tắc chọn API theo ý định

| Bạn muốn... | Nên sử dụng | Tránh nhầm với... |
|---|---|---|
| Plugin đặt giá trị mặc định có thể override | property.convention(value) | property.set(value) nếu người dùng cần quyền override rõ |
| Plugin đặt default lấy từ một nguồn khác | property.convention(provider) | provider.get() ngay khi cấu hình |
| Người dùng ghi đè bằng literal | property.set(value) | convention(value) |
| Người dùng ghi đè bằng nguồn động | property.set(provider) | map mà không nối vào Property |
| Giá trị mới được tính từ một nguồn | provider.map { ... } | get rồi ghép String sớm |
| Chọn một Provider khác theo trạng thái | provider.flatMap { ... } | map trả Provider lồng nhau |
| Kết hợp hai nguồn | first.zip(second) { a, b -> ... } | gọi get cho từng nguồn quá sớm |
| Có fallback khi nguồn thiếu | provider.orElse(value/provider) | kỳ vọng convention sẽ cứu explicit missing provider |
| Quay về default khi đã set | property.unset() | đổi default bằng set |
| Chặn thay cấu hình sau một thời điểm | finalizeValue()/finalizeValueOnRead()/disallowChanges() | nghĩ ba phương thức có cùng thời điểm đọc |
| Truy cập output file do task khác tạo | taskProvider.flatMap { it.outputFile } | tự lấy File bằng get hoặc provider tự chế làm mất task dependency |

**Thói quen tốt:** Trong plugin, khai báo managed property cho input/output, áp dụng convention cho default, cho build script set theo nhu cầu, dùng Provider để suy ra giá trị và nối trực tiếp vào task. Dùng get() chủ yếu tại điểm tiêu thụ hợp lệ, đặc biệt là TaskAction, khi Gradle cần giá trị thật.

## 11. Những lỗi phổ biến và hướng sửa

### Lỗi 1: Người dùng set rồi, nhưng plugin lại gọi convention và tưởng nó sẽ ghi đè

**Triệu chứng:** Plugin đặt convention('default'), user set('custom'), nhưng task vẫn dùng custom.

**Giải thích:** Đây là hành vi đúng. set là lựa chọn tường minh, convention là fallback. Nếu plugin bắt buộc một giá trị không thể thay, phải thiết kế hợp đồng rõ ràng và cơ chế kiểm tra/finalize phù hợp; không cố gọi convention liên tục để “ép” giá trị.

### Lỗi 2: Provider không có giá trị nhưng Property không rơi về convention

**Triệu chứng:** p.convention('A'); p.set(providers.gradleProperty('missing')); p.get() báo thiếu giá trị.

**Giải thích:** Bạn đã chọn explicit source là Provider không present. Dùng provider.orElse('B') trước khi set, hoặc bỏ explicit source bằng unset nếu thực sự muốn quay về convention.

### Lỗi 3: get() quá sớm

**Triệu chứng:** Giá trị được lấy trước khi plugin khác cấu hình xong; task dùng output sai hoặc configuration cache hoạt động kém.

**Cách sửa:** Thay biến String được chụp từ provider.get() bằng Provider được nối tới Property của task. Dùng map/flatMap/zip, để Gradle quyết định khi nào cần đọc giá trị.

### Lỗi 4: Nhầm map và flatMap

**Triệu chứng:** map { ... } trả một Provider thay vì String/File mong muốn, dẫn đến cấu trúc lồng hoặc sai kiểu.

**Cách sửa:** map cho phép biến đổi trả **giá trị thường**; flatMap dùng khi hàm biến đổi trả về **Provider**. Với output của một task, ưu tiên taskProvider.flatMap để giữ dependency.

### Lỗi 5: Sai kiểu Property

**Triệu chứng:** Property<Integer> nhận String không thể parse, hoặc Property<RegularFile> được gán đường dẫn thô không phù hợp.

**Cách sửa:** Dùng map chuyển kiểu theo quy tắc rõ ràng, ví dụ Integer.parseInt, và dùng RegularFileProperty/DirectoryProperty cùng layout API cho đường dẫn file. Không ép mọi cấu hình thành Property<String> nếu dữ liệu thực sự là số, boolean, file hoặc collection.

### Lỗi 6: Không khai báo @Input hoặc @OutputFile

**Triệu chứng:** Task output được cache/up-to-date sai, hoặc Gradle không biết input của consumer đến từ task nào.

**Cách sửa:** Tạo custom task type với managed Property và annotation tương ứng. Tránh đọc file tự phát trong cấu hình và task action mà không mô tả đầu vào/đầu ra.

### Lỗi 7: Muốn thay giá trị sau khi task bắt đầu chạy

**Triệu chứng:** set(...) ném IllegalStateException vì Property đã được finalized.

**Cách sửa:** Đặt cấu hình trước khi thực thi; không sửa input đang dùng khi task action chạy. Tách giá trị phát sinh trong execution thành output của task hoặc provider đúng mô hình.

### Lỗi 8: Coi convention của Property và precedence từ CLI là một

**Triệu chứng:** Nghĩ -P luôn “thắng” set trên một Property bất kể build script làm gì.

**Giải thích:** -P đặt **project property** trong hệ nguồn của providers.gradleProperty('key'). Nếu một Property khác đã set('literal') tường minh, việc -P đổi nguồn project property chỉ ảnh hưởng khi Property ấy **thật sự nối** với Provider đó. Thứ tự ưu tiên CLI/user/project là của project property; còn set/convention là của Property đang được cấu hình.

### Lỗi 9: Bảo rằng derived Provider luôn tự cập nhật sau khi finalize

**Triệu chứng:** Đã finalizeValue() nhưng mong Property theo dõi Provider nguồn ở các lần thay đổi sau.

**Cách sửa:** Hoãn finalize đến thời điểm thích hợp và giữ Provider wiring. Không sửa các input sau khi giá trị đã chốt.

### Lỗi 10: Khởi tạo một Provider tùy ý rồi tưởng Gradle tự thêm dependency task

**Triệu chứng:** Consumer chạy trước producer hoặc file output chưa tồn tại.

**Cách sửa:** Dùng output Property được đánh dấu @OutputFile/@OutputDirectory và taskProvider.flatMap; tránh tự bọc tham chiếu vào task bằng một providers.provider { ... } tách rời.

## 12. Bài tập tự đánh giá

**Bài 1 — Convention và set.** Một Property<String> mới được gọi p.convention('A'), p.set('B'), p.convention('C'). Khi p.get(), kết quả là gì và vì sao?

**Bài 2 — Provider thiếu.** p.convention('A') rồi p.set(providers.gradleProperty('unknown')), trong khi unknown không được khai báo. p.get() chắc chắn trả A không? Có hai hướng nào để sửa?

**Bài 3 — Giá trị được suy ra.** base có convention('order'), derived = base.map { it + '-service' }. Sau đó base.set('invoice') trước khi derived được truy vấn. Derived được kỳ vọng mang giá trị gì nếu chưa finalization?

**Bài 4 — Map và flatMap.** Một closure chọn Provider endpoint theo giá trị của environment. Nên dùng map hay flatMap? Tại sao?

**Bài 5 — Zip.** prefix có default 'Hi', recipient có default 'Alice', câu = prefix.zip(recipient) { a, b -> a + ' ' + b }. Khi recipient.set('Bob') được cấu hình hợp lệ trước khi chốt, câu sẽ là gì?

**Bài 6 — Fallback.** Một user muốn khi không có -Pregion thì dùng local, nhưng khi có -Pregion thì dùng giá trị CLI. Nên dùng providers.gradleProperty('region').orElse('local') hay set cứng 'local'?

**Bài 7 — Finalization.** Sau p.set(sourceProvider); p.finalizeValue(), sourceProvider được thay đổi. p còn tự lấy giá trị mới không? Khác gì với disallowChanges?

**Bài 8 — Task outputs.** Bạn cần nối outputFile (RegularFileProperty có @OutputFile) của task generate vào inputFile của task consume. Nên chọn taskProvider.flatMap { it.outputFile } hay gọi taskProvider.get().outputFile.get().asFile ngay trong configuration?

**Bài 9 — CLI và explicit set.** build script có output.set('manual'), còn sourceProvider lấy từ -Pname=cli. Nếu output không nối với sourceProvider thì -P có tự thay output thành cli không?

**Bài 10 — Task input.** Vì sao khai báo @Input Property<String> trên custom task đáng tin hơn việc để task tự đọc một String/biến toàn cục không có mô tả input?

### Gợi ý đáp án

1. **B**: set tường minh thắng convention, kể cả khi convention sau được thay thành C.
2. **Không**: Provider explicit không present có thể che convention; sửa bằng provider.orElse('B') trước set hoặc unset explicit source để quay về A.
3. **invoice-service**, miễn giá trị chưa bị chốt và chuỗi Provider còn được nối đúng.
4. **flatMap**, vì closure trả về Provider của endpoint được chọn.
5. **Hi Bob**.
6. Dùng providers.gradleProperty('region').orElse('local'), rồi nối Provider vào Property cần tiêu thụ theo set/convention phù hợp.
7. **Không**: finalize chốt giá trị và không theo dõi nguồn nữa; disallowChanges khóa việc sửa trực tiếp p nhưng chưa tự tính/chốt nguồn.
8. Dùng **taskProvider.flatMap { it.outputFile }** để giữ task dependency và lazy wiring.
9. **Không**: -P chỉ thay nguồn project property được đọc; output đã set literal tường minh.
10. @Input cho Gradle biết giá trị đầu vào để kiểm tra, chốt và quyết định việc thực thi; biến ngoài mô hình input có thể làm cache/up-to-date sai.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): Property, Provider, map/flatMap/zip/orElse và managed properties.
- [Gradle JavaDoc — Property](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Property.html): quy tắc chi tiết của set, convention, set(Provider), unset và finalize.
- [Gradle JavaDoc — SupportsConvention](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/SupportsConvention.html): unset và unsetConvention.
- [Gradle JavaDoc — HasConfigurableValue](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/HasConfigurableValue.html): finalizeValue, finalizeValueOnRead, disallowChanges.
- [Gradle User Manual — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): tránh get() quá sớm, nối output task qua Provider, khai báo input/output.
- [Gradle User Manual — Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): task type, annotation và cấu hình lazy.
- [Gradle User Manual — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): nguồn project properties, ví dụ -P, environment và gradle.properties.

**Ghi nhớ:** **convention** là mặc định; **set** chọn giá trị/nguồn tường minh; **map, flatMap và zip** suy ra Provider mới; **orElse** cung cấp fallback khi Provider thiếu. Hãy nối Provider vào Property có khai báo đầu vào và để Gradle truy vấn đúng thời điểm, thay vì get() sớm. Khi cần cố định giá trị, dùng finalization có chủ đích theo vòng đời cấu hình.