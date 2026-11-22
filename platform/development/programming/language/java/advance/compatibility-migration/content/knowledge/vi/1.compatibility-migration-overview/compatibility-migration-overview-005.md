# Đối tượng sử dụng module: ứng dụng, thư viện và nền tảng dùng chung

Khi lập kế hoạch nâng cấp hoặc chuyển đổi một module Java, cần xác định module đó đang phục vụ loại đối tượng nào. Một module có thể được đóng gói và sử dụng như một ứng dụng độc lập, được nhúng vào ứng dụng khác như một thư viện, hoặc tham gia vào một nền tảng dùng chung cho nhiều dự án. Ba cách sử dụng này tạo ra ba phạm vi tương thích khác nhau.

Ví dụ, một thay đổi khiến ứng dụng không khởi động được thường được phát hiện khi chạy thử và triển khai thử. Cùng thay đổi đó trong thư viện có thể khiến hàng chục ứng dụng không biên dịch được. Nếu nó nằm trong nền tảng dùng chung, ảnh hưởng có thể lan tới cả quá trình build, dependency và runtime của nhiều hệ thống. Vì vậy, không thể dùng một bộ tiêu chí duy nhất để kết luận mọi module đã sẵn sàng chuyển đổi.

## 1. Vì sao phải xác định đối tượng sử dụng?

Đối tượng sử dụng cho biết module được đưa vào hệ thống bằng cách nào, ai phụ thuộc vào nó và điều gì được xem là hợp đồng cần giữ ổn định. Thông tin này quyết định:

- **Phạm vi ảnh hưởng:** một tiến trình triển khai, các ứng dụng phụ thuộc, hay toàn bộ nhóm dự án dùng chung nền tảng.
- **Điểm kiểm tra tương thích:** khả năng khởi động, API công khai, dependency, cấu hình, dữ liệu hoặc quy tắc build.
- **Cách phát hành:** triển khai một ứng dụng, phát hành một phiên bản thư viện, hay phát hành đồng bộ một tập hợp thành phần nền tảng.
- **Cách chuyển đổi:** có thể nâng cấp và rollback độc lập hay cần phối hợp nhiều consumer.
- **Bằng chứng hoàn thành:** kiểm thử ứng dụng thực tế, kiểm thử consumer của thư viện, hay ma trận kiểm thử đại diện cho nhiều dự án.

Tên thư mục hoặc tên Gradle project chưa đủ để phân loại module. Một project có thể được gọi là `core`, `common` hoặc `platform` nhưng cách sử dụng thực tế mới quyết định hợp đồng tương thích của nó. Cần xem dependency graph, cách đóng gói, điểm khởi chạy, cấu hình triển khai và các consumer đang sử dụng artifact.

## 2. Module được sử dụng như một ứng dụng

Ứng dụng là một đơn vị có thể được khởi chạy và vận hành như một hệ thống hoặc một tiến trình độc lập. Nó thường có entry point, cấu hình môi trường, vòng đời chạy, tài nguyên cần cấp phát và quy trình triển khai riêng. Ứng dụng có thể sử dụng nhiều thư viện và dịch vụ khác, nhưng bản thân nó là đơn vị mà đội vận hành khởi động, giám sát, nâng cấp và rollback.

### 2.1. Hợp đồng của ứng dụng

Với ứng dụng, câu hỏi quan trọng là: sau khi chuyển đổi, ứng dụng có thể được build, khởi động, kết nối với các thành phần cần thiết và tiếp tục cung cấp hành vi đã cam kết hay không?

Các hợp đồng thường cần xem xét gồm:

| Hợp đồng | Nội dung cần bảo đảm |
|---|---|
| Build và đóng gói | Build tạo được artifact đúng loại; các task, plugin và công cụ build tương thích với môi trường mục tiêu. |
| JVM và runtime | JVM triển khai hỗ trợ bytecode, API Java và các thư viện mà ứng dụng sử dụng. |
| Khởi động | Entry point, auto-configuration, dependency injection và thứ tự khởi tạo vẫn hoạt động. |
| Cấu hình | Tên property, kiểu dữ liệu, giá trị mặc định, biến môi trường và cách nạp cấu hình không bị thay đổi ngoài dự kiến. |
| Giao tiếp | HTTP endpoint, message, sự kiện, giao thức và định dạng dữ liệu vẫn tương thích với consumer liên quan. |
| Dữ liệu | Truy vấn, schema, migration và cách đọc/ghi dữ liệu hoạt động trong giai đoạn chuyển tiếp. |
| Vận hành | Logging, metrics, tracing, health check, timeout, thread, memory và cách shutdown vẫn đáp ứng yêu cầu. |

Không nên chỉ kiểm tra ứng dụng có biên dịch thành công. Một ứng dụng có thể build được nhưng không khởi động do cấu hình thay đổi, không kết nối được database do driver không tương thích, hoặc chạy được nhưng trả về dữ liệu khác trước.

### 2.2. Cách đánh giá khi chuyển đổi ứng dụng

Trước khi thay đổi, ghi nhận môi trường chạy hiện tại: phiên bản JDK, cách khởi động, biến môi trường, cấu hình, dependency quan trọng và các dịch vụ bên ngoài. Sau đó xác định môi trường mục tiêu và kiểm tra từng điểm có thể thay đổi.

Một trình tự thực tế gồm:

1. Build ứng dụng bằng cấu hình mục tiêu và lưu lại log, artifact cùng kết quả kiểm tra.
2. Khởi động ứng dụng trong môi trường gần với môi trường triển khai thật.
3. Kiểm tra health check, kết nối database, cache, broker và các dịch vụ tích hợp.
4. Chạy smoke test cho các luồng nghiệp vụ quan trọng và kiểm tra hợp đồng API.
5. Kiểm tra log, metrics, lỗi runtime, mức sử dụng tài nguyên và hành vi khi shutdown.
6. Triển khai theo từng môi trường hoặc từng nhóm instance; chuẩn bị cách quay lại phiên bản trước nếu cần.

Nếu thay đổi có liên quan đến schema hoặc định dạng dữ liệu, phải xem xét khả năng chạy đồng thời phiên bản cũ và mới. Chẳng hạn, ứng dụng mới có thể được triển khai trong khi một số instance cũ vẫn đang xử lý request. Thay đổi dữ liệu chỉ an toàn khi cả hai phiên bản đều có thể hoạt động trong khoảng thời gian chuyển tiếp, hoặc khi đã có kế hoạch triển khai được kiểm soát.

## 3. Module được sử dụng như một thư viện

Thư viện là thành phần được ứng dụng hoặc module khác khai báo như một dependency. Thông thường, thư viện không tự tạo một tiến trình triển khai độc lập. Consumer đưa artifact của thư viện vào compile classpath và/hoặc runtime classpath để sử dụng các lớp, interface, annotation, resource hay dịch vụ mà thư viện cung cấp.

Ví dụ, một ứng dụng có thể khai báo dependency Gradle như sau:

```kotlin
dependencies {
    implementation("com.example:customer-client:2.4.0")
}
```

Ứng dụng consumer quyết định thời điểm khởi chạy và môi trường vận hành. Tuy nhiên, thay đổi trong thư viện vẫn có thể làm ứng dụng đó không biên dịch được, không liên kết được khi chạy hoặc thay đổi hành vi.

### 3.1. Hợp đồng của thư viện

Hợp đồng chính của thư viện là API và hành vi mà consumer dựa vào. Cần phân biệt một số khái niệm:

- **Tương thích mã nguồn (source compatibility):** mã nguồn consumer cũ vẫn biên dịch được khi dùng phiên bản thư viện mới.
- **Tương thích nhị phân (binary compatibility):** bytecode consumer đã biên dịch vẫn liên kết và chạy được với phiên bản thư viện mới trong phạm vi cam kết.
- **Tương thích hành vi (behavioral compatibility):** cùng lời gọi vẫn tạo ra kết quả, ngoại lệ và tác dụng phụ phù hợp với hợp đồng đã công bố.
- **Tương thích runtime:** thư viện và các dependency của nó có thể được nạp và chạy trên JVM cùng môi trường mà consumer hỗ trợ.

Các khái niệm này liên quan nhưng không thay thế cho nhau. Một thay đổi có thể vẫn biên dịch được nhưng làm kết quả tính toán khác đi. Ngược lại, mã nguồn consumer có thể cần chỉnh sửa dù một số bytecode đã biên dịch vẫn chạy được.

Những thay đổi dễ ảnh hưởng tới consumer gồm:

- Xóa, đổi tên hoặc giảm visibility của lớp, method, constructor hay field công khai.
- Đổi kiểu tham số hoặc kiểu trả về của method.
- Thay đổi interface mà consumer đang tự triển khai; ví dụ thêm method trừu tượng mới.
- Đổi cách ném exception, giá trị mặc định, thứ tự xử lý hoặc quy tắc xử lý `null`.
- Thay đổi annotation, generic contract, serialization format, resource path hoặc tên cấu hình mà consumer sử dụng.
- Nâng phiên bản Java hoặc dependency khiến môi trường của consumer không còn đáp ứng được yêu cầu tối thiểu.

Đặc biệt, việc thư viện biên dịch thành công trên JDK mới không chứng minh rằng mọi consumer đều có thể chạy nó. Nếu artifact được biên dịch thành bytecode của một phiên bản Java cao hơn JVM của consumer, consumer có thể gặp lỗi nạp lớp như `UnsupportedClassVersionError`. Thư viện cũng có thể gọi API chỉ xuất hiện ở JDK mới dù một phần mã nguồn trông vẫn tương thích.

### 3.2. Dependency và phạm vi API công khai

Thư viện thường có dependency trực tiếp và dependency bắc cầu. Consumer có thể chịu ảnh hưởng từ cả hai loại, kể cả khi consumer không khai báo trực tiếp dependency đó.

Với Gradle Java Library, cần phân biệt dependency được xuất ra như một phần API công khai với dependency chỉ phục vụ phần triển khai nội bộ. Ví dụ:

```kotlin
dependencies {
    api("com.example:public-model:1.2.0")
    implementation("com.example:internal-helper:3.1.0")
}
```

`api` phù hợp khi kiểu của dependency xuất hiện trong API công khai và consumer cần dependency đó trên compile classpath. `implementation` phù hợp với dependency chỉ dùng bên trong thư viện. Chọn sai phạm vi có thể làm lộ dependency không cần thiết, khiến consumer phải giải quyết xung đột phiên bản hoặc làm API khó sử dụng.

Khi chuyển đổi thư viện, hãy kiểm tra dependency tree, phiên bản tối thiểu, dependency bị loại trừ, xung đột phiên bản và các lớp mà consumer thực sự nhìn thấy. Một thay đổi dependency nội bộ vẫn có thể gây lỗi runtime nếu thư viện yêu cầu phiên bản mới có hành vi hoặc API khác.

### 3.3. Cách đánh giá khi chuyển đổi thư viện

Không nên chỉ chạy test bên trong repository của thư viện. Bộ test đó thường chỉ kiểm tra cách tác giả sử dụng thư viện, chưa chắc đại diện cho cách consumer bên ngoài đang sử dụng.

Nên kiểm tra:

1. API công khai trước và sau thay đổi, gồm lớp, method, constructor, interface, annotation và resource được hỗ trợ.
2. Khả năng biên dịch consumer mẫu trên các phiên bản JDK nằm trong phạm vi hỗ trợ.
3. Khả năng chạy bytecode consumer đã biên dịch trước đó nếu thư viện cam kết tương thích nhị phân.
4. Hành vi của các API quan trọng, bao gồm giá trị biên, exception, concurrency và serialization.
5. Dependency bắc cầu và khả năng giải quyết dependency trong một ứng dụng consumer thực tế.
6. Hướng dẫn nâng cấp, deprecation và phiên bản phát hành.

Nếu phải thay đổi API, có thể giữ API cũ trong một giai đoạn chuyển tiếp, bổ sung API mới, đánh dấu API cũ là deprecated và cung cấp hướng dẫn thay thế. Chỉ xóa API cũ khi chính sách phiên bản và phạm vi tương thích cho phép. Quyết định này cần dựa trên consumer thực tế và cam kết hỗ trợ của thư viện.

## 4. Module được sử dụng như một nền tảng dùng chung

Nền tảng dùng chung cung cấp quy ước, dependency, plugin, thư viện nền hoặc thành phần hạ tầng để nhiều ứng dụng và thư viện sử dụng nhất quán. Nền tảng có thể gồm một artifact duy nhất hoặc một tập hợp thành phần được quản lý theo phiên bản.

Ví dụ về thành phần nền tảng gồm:

- BOM hoặc Gradle platform để quản lý phiên bản dependency.
- Gradle convention plugin để chuẩn hóa cách cấu hình build.
- Bộ thư viện nền, starter hoặc adapter dùng chung.
- Cấu hình mặc định về logging, observability, bảo mật và kết nối dịch vụ.
- API hoặc client chung để các ứng dụng giao tiếp với hệ thống nội bộ.
- Quy tắc về JDK, Spring, plugin build và các dependency được phép sử dụng.

Nền tảng thường không phải là một ứng dụng nghiệp vụ có một entry point duy nhất. Nó có thể tác động ở thời điểm build, lúc biên dịch, khi khởi động ứng dụng hoặc trong suốt quá trình chạy. Vì thế, kiểm tra riêng một artifact của nền tảng là chưa đủ để đánh giá ảnh hưởng.

### 4.1. Hợp đồng của nền tảng

Hợp đồng của nền tảng gồm hai lớp:

1. **Hợp đồng của từng thành phần:** API, dependency, plugin, cấu hình và hành vi mà mỗi artifact cung cấp.
2. **Hợp đồng phối hợp:** các thành phần được kỳ vọng hoạt động cùng nhau theo một bộ phiên bản và quy ước thống nhất.

Một nền tảng có thể gây lỗi ngay cả khi từng thư viện riêng lẻ đều build được. Ví dụ, BOM có thể đưa vào một tổ hợp phiên bản không tương thích; convention plugin có thể thay đổi task hoặc compiler option; cấu hình mặc định có thể làm ứng dụng consumer thay đổi hành vi lúc khởi động.

Các câu hỏi cần trả lời khi chuyển đổi nền tảng:

- Những nhóm ứng dụng, thư viện và module nào đang sử dụng nền tảng trực tiếp hoặc gián tiếp?
- Nền tảng hỗ trợ những phiên bản JDK, Gradle, plugin và framework nào?
- Các artifact trong cùng bộ phát hành có yêu cầu dùng đồng bộ không?
- Quy tắc build hoặc cấu hình mặc định nào có thể làm thay đổi consumer?
- Có consumer nào cần được hỗ trợ trong giai đoạn chuyển tiếp không?
- Phiên bản cũ và mới có thể cùng tồn tại trong một hệ thống không?

### 4.2. Cách đánh giá khi chuyển đổi nền tảng

Phạm vi kiểm thử nên đại diện cho các kiểu consumer khác nhau, thay vì chỉ chọn một ứng dụng thuận tiện. Một ma trận đơn giản có thể gồm ứng dụng web, ứng dụng xử lý nền, thư viện được phát hành độc lập và một project sử dụng convention plugin. Tùy nền tảng, có thể cần thêm consumer dùng framework hoặc JDK khác nhau.

Quy trình đánh giá thường gồm:

1. Lập danh sách artifact, plugin, quy ước và cấu hình do nền tảng cung cấp.
2. Lập dependency graph để tìm consumer trực tiếp và gián tiếp.
3. Xác định ma trận phiên bản được hỗ trợ: JDK, Gradle, framework và dependency trọng yếu.
4. Build và kiểm thử các consumer đại diện bằng bộ phiên bản nền tảng mới.
5. Kiểm tra dependency resolution, task build, cấu hình mặc định và hành vi runtime.
6. Thử nâng cấp theo nhóm consumer, ghi nhận ngoại lệ và chuẩn bị lộ trình cho nhóm chưa thể nâng cấp.
7. Phát hành release notes nêu rõ thay đổi, phiên bản tương thích, bước migration và thời điểm ngừng hỗ trợ phiên bản cũ.

Nền tảng càng được nhiều consumer sử dụng thì chi phí của một thay đổi không tương thích càng lớn. Vì vậy, nên có quy tắc versioning rõ ràng, kiểm thử consumer đại diện và thời gian chuyển tiếp đủ để các nhóm dự án nâng cấp có kiểm soát.

## 5. So sánh ba kiểu sử dụng

| Khía cạnh | Ứng dụng | Thư viện | Nền tảng dùng chung |
|---|---|---|---|
| Cách được sử dụng | Khởi chạy và vận hành như một đơn vị độc lập | Được khai báo làm dependency của consumer | Nhiều project dùng bộ dependency, plugin, quy ước hoặc thành phần chung |
| Hợp đồng chính | Hành vi runtime, API dịch vụ, cấu hình và dữ liệu | API công khai, tương thích mã nguồn, nhị phân và hành vi | Hợp đồng của các thành phần và sự phối hợp giữa chúng |
| Đơn vị phát hành | Artifact và lần triển khai ứng dụng | Phiên bản artifact thư viện | Bộ phiên bản hoặc release train của nền tảng |
| Rủi ro điển hình | Không build, không khởi động, lỗi tích hợp hoặc thay đổi dữ liệu | Consumer không biên dịch, lỗi liên kết hoặc thay đổi hành vi | Nhiều consumer lỗi build/runtime do thay đổi dependency hay quy ước chung |
| Kiểm tra quan trọng | Smoke test, integration test, kiểm tra triển khai và vận hành | API check, consumer test, binary/runtime compatibility | Ma trận phiên bản, dependency convergence và kiểm thử nhiều consumer đại diện |
| Cách chuyển đổi | Triển khai theo môi trường hoặc nhóm instance | Phát hành phiên bản và hướng dẫn consumer nâng cấp | Chuyển đổi theo nhóm consumer, có lộ trình và quản lý phiên bản đồng bộ |

Ba loại này có thể xuất hiện cùng nhau trong một hệ thống. Một ứng dụng thường tiêu thụ nhiều thư viện; các thư viện đó có thể lại được quản lý bởi nền tảng dùng chung. Do đó, cần phân biệt **vai trò của module đang chuyển đổi** với **các loại consumer nằm phía sau nó**.

## 6. Một module có thể phục vụ nhiều loại consumer

Không phải module nào cũng chỉ có một kiểu sử dụng. Một thư viện nội bộ có thể được dùng bởi ứng dụng trong cùng repository, đồng thời được đóng gói để nhiều dự án khác sử dụng. Một thành phần nền tảng cũng có thể chứa thư viện runtime mà ứng dụng đưa trực tiếp vào classpath.

Trong trường hợp nhiều kiểu consumer cùng tồn tại, hãy ghi nhận từng hợp đồng riêng:

- Consumer chạy ứng dụng cần kiểm tra khởi động, cấu hình, tích hợp và vận hành.
- Consumer dùng thư viện cần kiểm tra API, dependency, bytecode và hành vi.
- Consumer dùng nền tảng cần kiểm tra tổ hợp phiên bản, quy ước build và tác động trên nhiều project.

Không nên gộp các kết quả thành một kết luận chung như “module tương thích” nếu chưa nêu rõ tương thích với loại consumer nào, phiên bản môi trường nào và trong điều kiện nào. Nếu ba vai trò có yêu cầu phát hành khác nhau, hãy cân nhắc tách artifact hoặc định nghĩa rõ profile sử dụng để tránh một thay đổi phục vụ consumer này làm hỏng consumer khác.

## 7. Cách xác định consumer thực tế

Phân loại phải dựa trên bằng chứng. Có thể bắt đầu từ các nguồn sau:

| Nguồn kiểm tra | Dấu hiệu cần tìm |
|---|---|
| Gradle settings và project dependency | Module nào phụ thuộc trực tiếp vào module đang xét; có dependency bắc cầu nào tiếp tục truyền nó tới consumer khác. |
| Khai báo dependency trong build file | Artifact được dùng như thư viện, platform/BOM hay plugin. |
| Source code | Có entry point, cấu hình khởi chạy, API công khai hoặc extension point cho consumer không. |
| Cấu hình và workflow triển khai | Có artifact được chạy, image được phát hành, service được deploy hoặc quy trình vận hành riêng không. |
| Dependency publication | Có artifact được publish để project khác sử dụng không; phiên bản nào đang được consumer khai báo. |
| Kiểm thử và CI | Những project nào build cùng, kiểm thử tích hợp hoặc xác nhận tương thích với module này. |
| Tài liệu sử dụng | Người dùng được hướng dẫn chạy ứng dụng, thêm dependency hay áp dụng bộ quy ước nền tảng. |

Nên phân biệt consumer trực tiếp và gián tiếp. Ví dụ, ứng dụng A phụ thuộc vào thư viện B, còn B phụ thuộc vào module C. C có thể không xuất hiện trong build file của A nhưng vẫn nằm trên runtime classpath của A. Khi thay đổi C, phạm vi ảnh hưởng có thể bao gồm A và những ứng dụng khác có cùng chuỗi dependency.

Một danh sách consumer hữu ích nên ghi rõ tên project, loại sử dụng, phiên bản đang dùng, môi trường JDK, cách nhận dependency, mức độ quan trọng và trạng thái kiểm thử. Nếu chưa tìm được consumer hoặc không thể xác minh một dependency bắc cầu, hãy ghi nhận đó là khoảng trống thông tin thay vì mặc định rằng module không có người sử dụng.

## 8. Quy trình chọn tiêu chí tương thích cho một lần chuyển đổi

Có thể áp dụng quy trình sau cho mỗi module:

### Bước 1: Mô tả vai trò hiện tại

Ghi rõ module là ứng dụng, thư viện, nền tảng dùng chung hay kết hợp nhiều vai trò. Mô tả cách module được build, đóng gói, phát hành và đưa vào hệ thống.

### Bước 2: Lập bản đồ consumer

Liệt kê consumer trực tiếp và gián tiếp. Với mỗi consumer, xác định phiên bản đang dùng, JDK/runtime, dependency liên quan và mức độ quan trọng đối với hệ thống.

### Bước 3: Chốt phạm vi hỗ trợ

Xác định môi trường hiện tại, môi trường mục tiêu và những phiên bản cần tiếp tục hỗ trợ. Phân biệt JDK dùng để chạy Gradle, JDK toolchain dùng để biên dịch và JDK dùng khi chạy ứng dụng; ba môi trường này có thể khác nhau.

### Bước 4: Xác định hợp đồng bị tác động

Chọn các hợp đồng tương ứng với vai trò: startup và vận hành cho ứng dụng; API và dependency cho thư viện; version alignment và quy ước build cho nền tảng. Bổ sung hợp đồng dữ liệu hoặc giao thức nếu module tham gia vào các luồng đó.

### Bước 5: Chọn bằng chứng kiểm thử

Mỗi rủi ro cần có một cách xác nhận. Ví dụ, thay đổi API cần consumer compile test; thay đổi bytecode cần kiểm tra runtime mục tiêu; thay đổi cấu hình cần startup/integration test; thay đổi BOM cần kiểm tra dependency resolution trên các consumer đại diện.

### Bước 6: Lập lộ trình phát hành và chuyển đổi

Quyết định cách đánh phiên bản, thời gian tương thích, nhóm consumer nâng cấp trước, cách xử lý consumer chưa sẵn sàng và điều kiện rollback. Với thay đổi không tương thích, release notes phải chỉ rõ điều gì thay đổi và consumer cần làm gì.

### Bước 7: Xác nhận sau chuyển đổi

Ghi nhận consumer nào đã nâng cấp, kết quả kiểm thử trên từng môi trường và những ngoại lệ còn tồn tại. Chỉ kết luận phạm vi đã hoàn tất khi có bằng chứng phù hợp với từng loại consumer trong phạm vi cam kết.

## 9. Ví dụ minh họa: nâng baseline Java

Giả sử một nhóm dự án muốn nâng baseline Java của một module từ Java 17 lên Java 21. Đây là ví dụ giả định để minh họa cách phân loại; quyết định thực tế còn phụ thuộc vào phạm vi hỗ trợ của từng dự án.

**Nếu module là ứng dụng:** cần bảo đảm môi trường triển khai có JVM phù hợp, image hoặc máy chủ đã được cập nhật, các dependency tương thích và quy trình khởi động hoạt động. Build thành công trên máy phát triển chưa chứng minh môi trường production đã sẵn sàng.

**Nếu module là thư viện:** cần xác định consumer nào vẫn chạy Java 17. Nếu thư viện phát hành bytecode chỉ chạy được trên Java 21, các consumer chạy Java 17 không thể nạp thư viện đó. Có thể cần giữ một nhánh hoặc phiên bản tương thích cũ, hoặc trì hoãn việc nâng baseline cho đến khi consumer đã chuyển đổi.

**Nếu module là nền tảng dùng chung:** cần kiểm tra tất cả nhóm consumer mà nền tảng hỗ trợ. Ngoài bytecode, phải xem xét Gradle wrapper, Gradle plugin, compiler toolchain, framework và dependency được quản lý. Một nhóm consumer có thể đã chạy Java 21 nhưng vẫn chưa thể nâng vì build plugin hoặc thành phần khác chưa tương thích.

Ví dụ này cho thấy cùng một thay đổi về Java baseline tạo ra các việc cần làm khác nhau. Phạm vi chuyển đổi phải được suy ra từ consumer và hợp đồng thực tế, không chỉ từ cấu hình compiler của module.

## 10. Checklist trước khi bắt đầu chuyển đổi

- [ ] Đã xác định module được sử dụng như ứng dụng, thư viện, nền tảng hay kết hợp nhiều vai trò.
- [ ] Đã tìm consumer trực tiếp và gián tiếp bằng dependency graph hoặc bằng chứng tương đương.
- [ ] Đã ghi nhận JDK dùng để build, biên dịch và chạy từng consumer.
- [ ] Đã xác định API, cấu hình, dependency, giao thức và dữ liệu có thể bị ảnh hưởng.
- [ ] Đã phân biệt tương thích mã nguồn, nhị phân, hành vi và runtime.
- [ ] Đã chọn consumer đại diện và cách kiểm thử phù hợp với từng vai trò.
- [ ] Đã xác định cách phát hành, lộ trình nâng cấp và điều kiện rollback.
- [ ] Đã ghi nhận các consumer hoặc môi trường chưa thể xác minh.

## Kết luận

Ứng dụng, thư viện và nền tảng dùng chung có cách tiêu thụ module và hợp đồng tương thích khác nhau. Ứng dụng tập trung vào khả năng build, khởi động, tích hợp và vận hành; thư viện tập trung vào API, dependency và khả năng tương thích với consumer; nền tảng tập trung vào sự nhất quán của nhiều thành phần và tác động trên nhiều project. Xác định đúng đối tượng sử dụng giúp khoanh vùng ảnh hưởng, chọn đúng kiểm thử và xây dựng lộ trình chuyển đổi có thể kiểm chứng.
