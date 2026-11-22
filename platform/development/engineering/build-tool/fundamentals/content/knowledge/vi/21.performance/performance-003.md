# Build lạnh, build ấm và điều kiện so sánh công bằng

Khi đánh giá hiệu năng Gradle, một câu hỏi thường gặp là: “Build mất bao lâu?”. Con số thời gian chỉ có ý nghĩa khi biết build bắt đầu từ trạng thái nào. Một lần chạy đầu tiên trên máy mới, một lần build sau khi đã tải dependency, một lần build không có file thay đổi và một lần build có thể khôi phục output từ build cache là những tình huống khác nhau.

**Build lạnh (cold build)** thường chỉ một lần chạy khi một hoặc nhiều lớp cache/trạng thái chưa được làm nóng. **Build ấm (warm build)** thường chỉ lần chạy sau khi daemon, dependency, cấu hình hoặc output đã được sử dụng trước đó. Hai thuật ngữ này không có một định nghĩa duy nhất áp dụng cho mọi benchmark. Vì vậy, cần mô tả chính xác trạng thái ban đầu thay vì chỉ ghi “cold” hoặc “warm”.

Một phép đo công bằng phải trả lời được: đang đo phần nào của build, cache nào được giữ, cache nào bị xóa hoặc vô hiệu hóa, task nào thực sự chạy, và các lần chạy có cùng điều kiện hay không. Nếu không, nhóm có thể kết luận sai rằng một thay đổi làm build nhanh hơn trong khi thực tế chỉ khác trạng thái cache hoặc môi trường.

## 1. Vì sao phải phân biệt build lạnh và build ấm?

Một Gradle build có nhiều nguồn chi phí:

- Khởi động JVM và Gradle daemon.
- Nạp class, khởi tạo plugin và thực hiện JIT compilation.
- Đọc settings/build scripts, tạo project model và task graph.
- Resolve dependency, tải metadata và artifact từ repository.
- Kiểm tra snapshot input/output và lịch sử task.
- Thực thi task như compile, test, code generation và packaging.
- Đọc/ghi file trên hệ thống lưu trữ.
- Khôi phục output từ local hoặc remote build cache.
- Chạy process bên ngoài, truy cập mạng hoặc tương tác với dịch vụ.

Lần chạy đầu tiên có thể phải trả chi phí cho nhiều bước cùng lúc. Lần chạy thứ hai có thể tận dụng daemon đang sống, dependency đã tải, configuration cache đã lưu, output vẫn còn và OS filesystem cache đã nóng. Nếu chỉ so sánh hai con số tổng thời gian, không thể biết phần nào tạo ra chênh lệch.

Ví dụ, một project chạy lần đầu mất 90 giây và lần thứ hai mất 8 giây. Không thể kết luận chỉ từ hai con số rằng Gradle đã tối ưu compile nhanh hơn 82 giây. Có thể lần đầu tải dependency, khởi tạo daemon, biên dịch toàn bộ và chạy test; lần thứ hai các task đều `UP-TO-DATE` và Gradle chỉ kiểm tra trạng thái.

## 2. “Cold” và “warm” có nhiều chiều độc lập

Không có một công tắc duy nhất biến toàn bộ build thành lạnh hoặc ấm. Cần xem từng lớp trạng thái.

| Lớp trạng thái | Lạnh thường có nghĩa là | Ấm thường có nghĩa là |
|---|---|---|
| Gradle daemon/JVM | Daemon chưa chạy hoặc process mới phải khởi động. | Daemon đã chạy, JVM đã nạp class và có thể đã JIT một phần. |
| Dependency cache | Dependency metadata/artifact chưa có trong Gradle User Home. | Dependency đã được resolve/tải và còn trong cache. |
| Project task outputs | Output chưa tồn tại hoặc đã bị xóa. | Output từ lần build trước vẫn tồn tại. |
| Task history | Workspace chưa có trạng thái thực thi phù hợp. | Gradle có snapshot/lịch sử để so sánh input/output. |
| Configuration cache | Chưa có entry phù hợp với build/configuration hiện tại. | Entry phù hợp có thể được tái sử dụng. |
| Build cache | Không có cache entry phù hợp hoặc cache bị tắt. | Local/remote cache có output phù hợp để khôi phục. |
| OS filesystem/page cache | Dữ liệu file có thể chưa nằm trong memory cache. | Các file vừa đọc có thể còn trong page cache của hệ điều hành. |
| Repository/network | Metadata và artifact cần được lấy qua mạng. | Cache local hoặc mirror giảm nhu cầu truy cập mạng. |

Một lần chạy có thể lạnh ở một lớp nhưng ấm ở lớp khác. Ví dụ, `clean build` có thể xóa output project nhưng vẫn giữ dependency cache, daemon và configuration cache. Đây là “build lại từ output sạch với dependency cache ấm”, không phải một cold build hoàn toàn.

Khi báo cáo benchmark, nên mô tả trạng thái từng lớp quan trọng thay vì gắn một nhãn chung.

## 3. Phân biệt các loại cache của Gradle

Những cơ chế dưới đây thường bị gọi chung là “Gradle cache”, nhưng chúng giữ dữ liệu khác nhau và tác động đến thời gian build theo cách khác nhau.

### 3.1. Dependency cache

Gradle lưu metadata và artifact đã resolve trong Gradle User Home, thường là thư mục `~/.gradle/caches` trên Unix-like systems hoặc thư mục `.gradle` trong user profile trên Windows.

Dependency cache giúp tránh tải lại JAR/POM/module metadata ở mỗi lần build. Nếu cache còn hợp lệ, Gradle có thể resolve dependency nhanh hơn và giảm truy cập repository.

`clean` không xóa dependency cache. Vì vậy:

```bash
./gradlew clean build
```

thường vẫn dùng các dependency đã tải trước đó. Lệnh này không đo thời gian tải dependency trên một máy chưa có cache.

`--refresh-dependencies` yêu cầu Gradle refresh dependency metadata/cache theo quy tắc resolution. Nó không tương đương với một Gradle User Home hoàn toàn mới và không nên được dùng như cách chuẩn để tạo mọi loại cold build.

### 3.2. Task outputs và task history

Task outputs thường nằm trong thư mục `build/` của từng project. Gradle dùng input/output snapshot và execution history để xác định task có thể `UP-TO-DATE` hay cần chạy lại.

Task `clean` thường xóa build directory của project. Nó không xóa toàn bộ Gradle User Home, không xóa dependency cache và không nhất thiết xóa project-local state như configuration cache trong `.gradle`.

Sau `clean`, các task tạo output sẽ phải chạy lại hoặc có thể lấy output từ build cache nếu task cacheable và cache entry phù hợp. Vì vậy, bật build cache khi benchmark `clean build` có thể tạo kết quả `FROM-CACHE` thay vì thực thi compiler/task action.

### 3.3. Configuration cache

Configuration cache lưu kết quả cấu hình build để Gradle có thể bỏ qua hoặc giảm đáng kể việc thực hiện lại configuration phase trong những lần chạy phù hợp.

Lần đầu dùng:

```bash
./gradlew build --configuration-cache
```

Gradle có thể tạo configuration cache entry. Lần chạy sau với cùng build logic, task request và các input configuration tương thích có thể tái sử dụng entry đó:

```bash
./gradlew build --configuration-cache
```

Nếu build script, plugin hoặc input configuration thay đổi, entry có thể bị invalidated và Gradle phải cấu hình lại. Nếu build chưa tương thích configuration cache, Gradle có thể báo vấn đề và không thể tái sử dụng như mong đợi.

Configuration cache không phải build cache. Nó lưu trạng thái cấu hình/task graph phù hợp, không thay thế output của compile/test task.

### 3.4. Build cache

Build cache lưu output của các task cacheable theo cache key được tính từ implementation và input đã khai báo. Nếu key phù hợp, Gradle có thể khôi phục output thay vì chạy task action.

Build cache có thể là local hoặc remote. Local build cache thường dùng trong Gradle User Home; remote build cache có thể chia sẻ output giữa các máy hoặc CI job.

Một task báo `FROM-CACHE` có nghĩa output được khôi phục từ cache. Điều này khác với `UP-TO-DATE`, khi output hiện tại đã hợp lệ và Gradle không cần chạy action.

### 3.5. Daemon và JVM warm-up

Gradle daemon là process nền có thể được tái sử dụng giữa các lần build. Daemon giúp tránh chi phí khởi động JVM và giữ lại một số trạng thái process. JVM cũng có thể tối ưu code qua JIT sau khi các đường code được thực thi nhiều lần.

Lần build đầu sau khi daemon khởi động thường chịu chi phí startup, class loading và khởi tạo plugin. Những lần tiếp theo có thể nhanh hơn dù task graph và output không thay đổi.

### 3.6. OS filesystem cache

Hệ điều hành có thể giữ nội dung file vừa đọc trong memory cache. Khi build đọc lại cùng source, JAR hoặc metadata, thao tác đọc có thể nhanh hơn do không cần truy cập storage vật lý.

OS page cache nằm ngoài quản lý trực tiếp của Gradle. Cách xóa cache khác nhau theo hệ điều hành, thường cần quyền quản trị và có thể ảnh hưởng các process khác. Trong benchmark thông thường, nên ghi nhận đây là một yếu tố môi trường và giữ điều kiện chạy nhất quán, thay vì tùy tiện xóa page cache trước mỗi lần đo.

## 4. Các kịch bản build cần đo riêng

Một benchmark hữu ích thường có nhiều kịch bản thay vì một con số tổng hợp.

| Kịch bản | Trạng thái ban đầu | Câu hỏi được trả lời |
|---|---|---|
| First build trên môi trường mới | Workspace và Gradle User Home mới, daemon mới, dependency chưa có cache. | Người dùng/CI mới phải chờ bao lâu để build lần đầu? |
| Clean build với dependency cache ấm | Build outputs đã xóa; dependency cache có sẵn. | Chi phí compile/test/package đầy đủ khi không tính tải dependency ban đầu là bao nhiêu? |
| Warm no-change build | Output còn nguyên, task history và daemon đã có; không sửa input. | Build kiểm tra trạng thái và kết thúc khi mọi task up-to-date mất bao lâu? |
| Warm incremental build | Build đã chạy; một input cụ thể thay đổi. | Một thay đổi nhỏ khiến những task nào chạy và mất bao lâu? |
| Build cache restore | Output local không có nhưng cache entry phù hợp tồn tại. | Có thể tiết kiệm bao nhiêu thời gian nhờ local/remote cache? |
| Configuration cache reuse | Entry cấu hình phù hợp đã được tạo. | Có thể giảm chi phí configuration phase bao nhiêu? |
| Daemon cold, dependency warm | Daemon mới nhưng dependency cache vẫn có. | Chi phí JVM/Gradle startup trong môi trường đã có dependency là bao nhiêu? |

Không nên gộp các kịch bản này thành một “build time” duy nhất. Chúng đại diện cho trải nghiệm khác nhau: CI mới, CI có cache, developer lặp lại build, chỉnh sửa một file hoặc build ở workspace khác.

## 5. Kịch bản first build trên môi trường mới

Kịch bản này mô phỏng máy mới hoặc CI runner chưa có Gradle User Home cache.

Trạng thái cần mô tả:

- Workspace được checkout mới hoặc chưa có project build state.
- Gradle User Home là thư mục mới, không có dependency cache và local build cache cũ.
- Daemon chưa được khởi động.
- Configuration cache chưa có entry.
- Không có output project từ lần chạy trước.
- Repository/network và quyền truy cập tương đương môi trường thực tế.

Trên PowerShell có thể dùng một Gradle User Home riêng cho thí nghiệm:

```powershell
$env:GRADLE_USER_HOME = "$env:TEMP\gradle-home-cold-01"
.\gradlew.bat build --no-build-cache --no-configuration-cache
```

Mỗi lần đo cold dependency nên dùng một Gradle User Home mới hoặc một môi trường đã được reset theo quy trình kiểm soát. Nếu tái sử dụng cùng thư mục sau lần đầu, các lần tiếp theo không còn là cold dependency run.

Kịch bản này bao gồm thời gian tải Gradle distribution nếu wrapper distribution chưa có, resolve plugin và dependency, khởi động JVM, cấu hình build và thực thi task. Nếu mục tiêu là đo trải nghiệm first build của người dùng, giữ các chi phí này là hợp lý. Nếu mục tiêu chỉ là đo tốc độ compile, cần một kịch bản khác để không trộn network/startup vào phép đo.

Không xóa Gradle User Home thật của người dùng để tạo thí nghiệm. Dùng thư mục thử nghiệm riêng giúp giữ nguyên cache cá nhân và tránh làm ảnh hưởng những project khác.

## 6. Clean build với dependency cache ấm

Đây là kịch bản thường được dùng để đo chi phí thực thi đầy đủ của project khi dependency đã có sẵn.

Ví dụ:

```bash
./gradlew clean build --no-build-cache --no-configuration-cache
```

Lệnh này:

- Xóa output thuộc build directory thông qua task `clean`.
- Giữ dependency cache trong Gradle User Home.
- Tắt build cache để task cacheable phải tạo output trong lần chạy này.
- Tắt configuration cache để không tái sử dụng kết quả configuration phase.
- Vẫn có thể dùng daemon hiện tại, trừ khi môi trường được reset riêng.

Đây không phải cold build hoàn toàn. Đây là một phép đo clean execution với dependency cache ấm và configuration cache bị tắt.

Nếu muốn đo clean build có configuration cache reuse, hãy tạo entry trước và chạy lại cùng điều kiện. Khi đó cần ghi rõ lần đo đang tái sử dụng configuration cache.

Lưu ý: `clean` thường là task trong task graph. Không nên tự xóa thư mục `build/` trong lúc Gradle đang chạy hoặc khi các process build khác đang dùng cùng workspace.

## 7. Warm no-change build

Warm no-change build mô phỏng lập trình viên chạy lại cùng lệnh sau khi build đã thành công và không có input thay đổi.

Ví dụ:

```bash
./gradlew build --configuration-cache --build-cache
./gradlew build --configuration-cache --build-cache
```

Lần đầu có thể cấu hình build, tải dependency còn thiếu, thực thi task và tạo configuration cache. Lần thứ hai có thể tái sử dụng configuration cache; nhiều task có output hợp lệ sẽ được đánh dấu `UP-TO-DATE`.

Kịch bản này đo chi phí của một lần build lặp lại không có thay đổi. Nó hữu ích để đánh giá trải nghiệm developer khi chạy build liên tục, nhưng không đại diện cho thời gian compile/test đầy đủ.

Khi đọc kết quả, kiểm tra task outcomes:

- `UP-TO-DATE`: task không cần chạy lại vì output hiện tại còn hợp lệ.
- `FROM-CACHE`: output được khôi phục từ build cache.
- `SUCCESS`: task action đã thực thi thành công.
- `NO-SOURCE`: task không có source phù hợp để xử lý.
- `SKIPPED`: task bị bỏ qua theo điều kiện.

Nếu warm build nhanh vì hầu hết task `UP-TO-DATE`, đó là một kết quả hợp lệ cho kịch bản no-change. Không được diễn giải thành compile nhanh hơn nếu compiler thực tế không chạy.

## 8. Warm incremental build sau một thay đổi nhỏ

Đây thường là kịch bản có ý nghĩa lớn với vòng lặp phát triển hằng ngày. Quy trình:

1. Chạy build ban đầu để tạo output và task history.
2. Thay đổi đúng một input đã xác định, ví dụ một file Java hoặc resource.
3. Chạy lại cùng task request.
4. Ghi lại task nào chạy, task nào `UP-TO-DATE` và thời gian tổng thể.

Ví dụ:

```bash
./gradlew test
```

Sau khi chỉnh một file Java, chạy:

```bash
./gradlew test --info
```

Kết quả có thể gồm compile task liên quan được thực thi, task không phụ thuộc thay đổi vẫn `UP-TO-DATE`, và test task chạy lại theo dependency/output model. Gradle compiler có thể thực hiện incremental compilation nếu task/compiler hỗ trợ và điều kiện phù hợp.

Không nên thay đổi nhiều file không liên quan trong cùng một lần benchmark incremental nếu muốn hiểu tác động của một thay đổi. Cũng cần kiểm soát nội dung thay đổi để mỗi lần đo bắt đầu từ cùng một baseline.

## 9. Build cache restore là một kịch bản riêng

Build cache có thể khôi phục output khi task không thể dùng output local nhưng có cache entry tương ứng. Đây là tình huống thường gặp ở CI khi runner mới được tạo nhưng remote cache được chia sẻ.

Để đo cache restore:

- Dùng cùng source revision và cùng task inputs đã tạo cache entry trước đó.
- Xóa output local hoặc dùng workspace mới.
- Giữ remote/local build cache được cấu hình và truy cập được.
- Bật build cache.
- Quan sát task outcome `FROM-CACHE`.

Ví dụ lệnh có thể là:

```bash
./gradlew build --build-cache --no-configuration-cache
```

Lệnh này chỉ bật build cache; để chắc chắn đo cache restore, cần chuẩn bị workspace và cache state phù hợp. Nếu output local vẫn tồn tại và hợp lệ, task có thể `UP-TO-DATE` thay vì `FROM-CACHE`.

Không nên gọi kết quả cache restore là “warm no-op build”. Một no-op build giữ output local; cache restore tái tạo output từ cache entry. Hai tình huống có thể có thời gian và chi phí I/O rất khác nhau.

## 10. Đo riêng configuration cache và task execution

Configuration cache giảm chi phí cấu hình. Nó có thể tác động mạnh đến build lớn có nhiều project/plugin và task registration, đặc biệt khi task execution vốn ngắn.

Để đo configuration cache:

1. Chọn cùng task request và cùng build revision.
2. Chạy lần đầu với `--configuration-cache` để tạo entry.
3. Chạy lại cùng request và cùng input configuration.
4. Xác nhận log cho biết configuration cache được reused.
5. So sánh với lần chạy dùng `--no-configuration-cache` trong cùng điều kiện cache khác được kiểm soát.

Không thể kết luận configuration cache cải thiện bao nhiêu chỉ từ lần đầu bật nó, vì lần đầu phải trả chi phí tạo cache entry. Cần phân biệt lần store và lần reuse.

Tương tự, khi muốn đo build cache, phải phân biệt lần tạo cache entry (task thực thi và lưu output) với lần lấy output từ cache. Đo một lần store và một lần hit rồi gộp thành một trung bình sẽ che mất hành vi của từng trường hợp.

## 11. `clean`, `--rerun-tasks`, `--no-build-cache` và `--refresh-dependencies` không giống nhau

Các lệnh/tùy chọn sau thường bị dùng thay thế nhau khi muốn “làm lạnh build”, nhưng chúng thay đổi trạng thái khác nhau.

| Lệnh/tùy chọn | Tác động chính | Không làm gì? |
|---|---|---|
| `clean` | Xóa build outputs thuộc phạm vi clean task. | Không xóa dependency cache, Gradle daemon, configuration cache hoặc toàn bộ build cache. |
| `--rerun-tasks` | Yêu cầu thực thi lại các task trong graph thay vì dựa vào up-to-date state. | Không xóa dependency cache hoặc tạo Gradle User Home mới. |
| `--no-build-cache` | Tắt đọc/ghi build cache cho lần chạy. | Không tắt up-to-date checking hoặc configuration cache. |
| `--no-configuration-cache` | Không sử dụng configuration cache cho lần chạy. | Không tắt dependency cache, build cache hoặc task up-to-date checking. |
| `--refresh-dependencies` | Yêu cầu refresh dependency metadata/artifact cache theo cơ chế Gradle. | Không xóa sạch mọi cache và không đảm bảo mọi artifact đều phải tải lại. |
| `--stop` | Dừng các Gradle daemon tương ứng với Gradle version được gọi. | Không xóa dependency cache, task outputs hay cache files. |
| `--no-daemon` | Không dùng persistent daemon theo yêu cầu; Gradle có thể vẫn khởi chạy single-use daemon để đáp ứng JVM settings. | Không đảm bảo bỏ mọi chi phí JVM startup hoặc làm lạnh dependency/task caches. |

Ví dụ, `clean --no-build-cache` là một cách tạo điều kiện để task outputs được tạo lại thay vì lấy từ build cache. Nó vẫn có thể dùng dependency cache và daemon đang hoạt động.

`--rerun-tasks` hữu ích khi muốn buộc task chạy lại để điều tra. Tuy nhiên, nếu task có side effect hoặc tốn thời gian lớn, không nên dùng nó như benchmark warm no-change vì nó cố tình loại bỏ lợi ích up-to-date checking.

## 12. Điều kiện so sánh công bằng giữa hai thay đổi

Khi so sánh hai nhánh code, hai phiên bản Gradle, hai plugin hoặc hai cấu hình build, cần kiểm soát các biến có thể ảnh hưởng thời gian.

### 12.1. Cùng phần cứng và môi trường

- Cùng máy hoặc cùng loại runner với CPU, RAM và storage tương đương.
- Cùng hệ điều hành, filesystem và power mode.
- Không chạy các workload CPU/disk/network lớn khác đồng thời.
- Cùng JDK distribution và version cho daemon/compiler/runtime liên quan.
- Cùng Gradle Wrapper version, trừ khi chính version Gradle là biến đang được thử nghiệm.
- Cùng JVM args, heap size, worker count và parallel execution settings.

Nếu mục tiêu là so sánh Gradle version, giữ nguyên các điều kiện còn lại và chỉ thay Gradle Wrapper version. Nếu mục tiêu là so sánh `--parallel`, không đổi đồng thời heap, daemon, test set hoặc cache policy.

### 12.2. Cùng source và task request

- Dùng cùng commit hoặc cùng nội dung source tree.
- Dùng cùng task request, ví dụ `build`, `test` hoặc `:app:assemble`.
- Dùng cùng project properties, environment variables và build parameters.
- Dùng cùng test filters, test data và external services.
- Dùng cùng dependency lock state và repository/mirror nếu đang đo task execution.
- Không để một nhánh có thêm generated file hoặc output từ lần build trước.

### 12.3. Cùng trạng thái cache

Trước khi đo, xác định rõ từng cache được giữ hay reset:

- Gradle daemon: reused hay fresh process?
- Dependency cache: warm hay fresh Gradle User Home?
- Task outputs/history: giữ nguyên hay clean workspace?
- Configuration cache: entry được reuse hay bị tắt/invalidated?
- Build cache: disabled, local hit hay remote hit?
- OS filesystem cache: không kiểm soát được hay có quy trình kiểm soát cụ thể?

Không so sánh một lần chạy A có dependency cache ấm với một lần chạy B phải tải dependency từ mạng. Đó không phải phép đo công bằng của tốc độ build logic.

### 12.4. Cùng network và repository conditions

Nếu benchmark bao gồm dependency resolution, hãy kiểm soát repository endpoint, mirror, proxy, DNS và tốc độ mạng. Một lần tải artifact bị throttling hoặc repository tạm thời chậm có thể làm sai kết quả.

Nếu benchmark không nhằm đo network, nên chuẩn bị dependency cache trước và dùng cùng trạng thái warm cache cho cả hai trường hợp. Không dùng dynamic versions hoặc changing modules không được khóa nếu chúng có thể resolve ra metadata khác giữa các lần chạy.

## 13. Warm-up, số lần chạy và cách tổng hợp kết quả

Một lần đo không đủ để kết luận. Thời gian build có thể dao động do JIT, GC, filesystem, scheduler, antivirus, network hoặc workload nền.

Một quy trình đo warm build có thể gồm:

1. Chuẩn bị workspace và cache state đúng kịch bản.
2. Chạy một hoặc vài lần warm-up không tính vào kết quả.
3. Chạy nhiều iteration với cùng task request và không thay đổi input.
4. Ghi wall-clock time và task outcomes từng iteration.
5. Tính median và ghi thêm min/max hoặc percentile nếu số lần đo đủ lớn.
6. Lặp lại cho cấu hình còn lại trong cùng điều kiện.

Median thường ít bị ảnh hưởng bởi một lần chạy bất thường hơn arithmetic mean. Tuy nhiên, không nên chỉ công bố median nếu các lần đo dao động rất lớn; hãy báo cả độ phân tán và điều tra nguyên nhân.

Với cold build, mỗi iteration phải được reset về cùng trạng thái cold. Nếu chỉ reset ở iteration đầu, các iteration tiếp theo đã trở thành warm run. Có thể tạo workspace/Gradle User Home riêng cho mỗi lần đo, hoặc dùng một quy trình reset có kiểm soát và ghi rõ chi phí reset có được tính vào thời gian hay không.

## 14. Đo những gì ngoài tổng thời gian?

Wall-clock time là số liệu quan trọng với người dùng, nhưng chưa đủ để giải thích nguyên nhân.

| Số liệu | Nó cho biết gì? |
|---|---|
| Total wall-clock time | Thời gian từ lúc gọi lệnh đến khi Gradle kết thúc. |
| Configuration time | Chi phí settings/build scripts/plugin configuration. |
| Task execution time | Thời gian thực thi các task action. |
| Critical path | Chuỗi task phụ thuộc quyết định thời gian hoàn thành tổng thể. |
| Task outcomes | Task nào `SUCCESS`, `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hoặc `SKIPPED`. |
| CPU utilization | Build bị giới hạn bởi CPU hay có nhiều thời gian chờ. |
| Memory/GC | Heap pressure, garbage collection và nguy cơ thiếu RAM. |
| Disk I/O | Chi phí đọc/ghi source, JAR và output. |
| Network traffic | Dependency download hoặc tương tác dịch vụ ngoài. |

Nếu total time giảm nhưng task execution time không đổi, cải thiện có thể đến từ configuration cache, daemon warm-up hoặc dependency resolution. Nếu task execution giảm, hãy xem task nào thay đổi outcome hoặc thực thi nhanh hơn.

## 15. Công cụ đo hiệu năng Gradle

### 15.1. Gradle `--profile`

Gradle có thể tạo profile report:

```bash
./gradlew build --profile
```

Report thường được tạo trong `build/reports/profile/`. Nó cung cấp thông tin về thời gian configuration, task và một số hoạt động build. Profile có overhead và không nên được dùng làm thời gian chuẩn duy nhất cho benchmark cực ngắn; hãy dùng cùng tùy chọn cho cả hai lần so sánh.

### 15.2. `--info` và `--debug`

`--info` hữu ích để xem task outcome và một số chi tiết về cache/up-to-date. `--debug` tạo log rất lớn và có thể làm thay đổi thời gian đo đáng kể. Dùng log chi tiết để chẩn đoán, còn phép đo thời gian chính nên chạy với mức logging nhất quán và tối thiểu.

### 15.3. Gradle Profiler

Gradle Profiler là công cụ chuyên dụng để benchmark Gradle build. Nó hỗ trợ mô tả scenario, warm-up, iteration và các kiểu thay đổi source nhằm mô phỏng build thực tế. Công cụ này phù hợp khi cần so sánh configuration cache, incremental build, build cache hoặc thay đổi build logic một cách lặp lại.

Khi dùng Gradle Profiler, cần đọc cấu hình scenario và xác nhận chính xác nó chuẩn bị workspace/cache ra sao. Không giả định mọi scenario mặc định đều mô phỏng cùng một loại cold/warm state.

### 15.4. Build scans

Build scan có thể cung cấp phân tích task, configuration, cache và môi trường chi tiết. Khi sử dụng, tuân theo chính sách bảo mật của tổ chức vì build scan có thể gửi dữ liệu build đến dịch vụ scan được cấu hình. Không đưa secret, token hoặc dữ liệu nhạy cảm vào log/build scan.

## 16. Một kế hoạch benchmark có thể tái lập

Giả sử nhóm muốn so sánh hai phiên bản convention plugin và mục tiêu là biết tác động đến trải nghiệm developer.

Có thể thiết kế các scenario sau:

| Scenario | Chuẩn bị | Lệnh đo | Điều cần ghi |
|---|---|---|---|
| First build | Workspace mới, Gradle User Home mới. | `./gradlew build --no-build-cache --no-configuration-cache` | Tổng thời gian, dependency downloads, task outcomes. |
| Clean execution | Dependency cache warm, output sạch, build cache/configuration cache tắt. | `./gradlew clean build --no-build-cache --no-configuration-cache` | Thời gian thực thi compile/test/package. |
| Warm no-change | Build đã chạy thành công, không đổi input. | `./gradlew build --configuration-cache --build-cache` | Configuration cache reuse, số task up-to-date. |
| Incremental source edit | Build baseline đã tạo output; sửa một source file xác định. | `./gradlew test --info` | Task bị invalidated, compile/test time. |
| Remote cache restore | Workspace mới, remote cache đã có output cho cùng inputs. | `./gradlew build --build-cache` | Số task `FROM-CACHE`, thời gian tải cache. |

Với mỗi scenario, chạy nhiều iteration phù hợp và ghi rõ warm-up. Đối với first build, dùng một Gradle User Home riêng cho từng iteration. Đối với warm no-change, không chạy `clean` giữa các iteration vì như vậy sẽ thay đổi kịch bản.

## 17. Ví dụ đọc kết quả benchmark

Giả sử hai cấu hình A và B có kết quả minh họa:

| Scenario | Cấu hình A | Cấu hình B | Nhận xét |
|---|---:|---:|---|
| First build, dependency cache cold | 120 s | 118 s | Chênh lệch nhỏ; tải dependency/network có thể chi phối. |
| Clean execution, dependency cache warm | 72 s | 61 s | Có thể có cải thiện ở task execution hoặc graph. Cần xem profile. |
| Warm no-change | 9 s | 4 s | Cần xác nhận configuration cache/task outcomes; phần lớn task có thể đã up-to-date. |
| Incremental source edit | 18 s | 13 s | Xem task graph bị invalidated và compiler/test execution. |
| Remote cache restore | 14 s | 8 s | Xem số task FROM-CACHE và chi phí tải output. |

Các số liệu trên chỉ để minh họa cách phân tích, không phải kết quả benchmark thực tế. Không nên kết luận B nhanh hơn trong mọi tình huống chỉ vì B có số thấp hơn ở một scenario. Nếu người dùng chủ yếu làm việc với warm incremental build, scenario đó cần trọng số cao hơn first build; nếu CI runner mới thường xuyên được tạo, cold/remote-cache scenario lại quan trọng hơn.

Khi thấy khác biệt, hãy kiểm tra:

- Task nào được thực thi ở A nhưng up-to-date hoặc from-cache ở B?
- Có task nào bị loại khỏi graph hoặc test bị skip không?
- Cấu hình B có thay đổi output/coverage/test behavior không?
- Dependency graph có giống nhau không?
- Configuration cache có được reuse ở cả hai không?
- Có khác biệt về network, daemon, JDK hoặc machine load không?

Hiệu năng chỉ có ý nghĩa nếu build vẫn làm cùng một công việc và tạo cùng artifact/chất lượng kiểm tra.

## 18. Những phép so sánh không công bằng thường gặp

### 18.1. So sánh first run với second run

Lần đầu có thể phải tải dependency và khởi động daemon; lần hai dùng cache. Chênh lệch không thể được quy hoàn toàn cho thay đổi code.

### 18.2. Chỉ chạy `clean` ở một bên

Một bên phải compile/package lại, bên còn lại có output `UP-TO-DATE`. Kết quả đo không cùng trạng thái ban đầu.

### 18.3. Bật build cache ở một bên

Một cấu hình có thể khôi phục output từ cache, trong khi cấu hình kia thực thi task. Đây là benchmark cache policy, không phải so sánh thuần tốc độ thực thi task.

### 18.4. Chỉ bật configuration cache ở một bên

Chênh lệch có thể đến từ configuration phase được reuse. Nếu đang so sánh plugin implementation, cần xác định có muốn đo cả tác động configuration cache hay không và giữ điều kiện nhất quán.

### 18.5. Chạy hai benchmark song song trên cùng máy

Hai build cạnh tranh CPU, disk, RAM, daemon và network. Thời gian mỗi bên không còn phản ánh hiệu năng khi chạy riêng. Hãy chạy tuần tự hoặc dùng runner riêng biệt có cấu hình tương đương.

### 18.6. Thay đổi nhiều yếu tố cùng lúc

Ví dụ đổi Gradle version, JDK, worker count, parallel mode và heap size trong cùng một lần thử. Khi kết quả thay đổi, không thể xác định yếu tố nào tạo ra tác động. Chỉ thay một biến mỗi lần hoặc thiết kế factorial experiment có chủ đích.

### 18.7. Dùng `--debug` cho một bên nhưng không dùng bên kia

Log debug có overhead và I/O lớn. Logging khác nhau làm benchmark lệch. Dùng cùng mức log và cùng công cụ đo cho các trường hợp.

### 18.8. Quên kiểm tra task outcomes

Build có thể nhanh hơn vì test không chạy, source set rỗng, task bị `onlyIf` skip hoặc task graph thiếu dependency. Luôn xác nhận hai build thực hiện cùng công việc.

## 19. Cách báo cáo kết quả để người khác có thể kiểm chứng

Một báo cáo benchmark nên ghi:

- Mục tiêu đo: first build, clean execution, warm no-change, incremental hay cache restore.
- Commit/source revision và task request.
- Gradle Wrapper version, JDK version và OS.
- CPU, RAM, storage và runner type.
- JVM args, parallel/worker settings và environment variables quan trọng.
- Trạng thái daemon, dependency cache, task outputs, configuration cache, build cache và network.
- Cách chuẩn bị/reset state trước mỗi iteration.
- Số lần warm-up và số lần đo.
- Kết quả từng iteration, median và độ phân tán.
- Task outcomes, configuration/task execution time và các thay đổi về graph.
- Những khác biệt hoặc giới hạn chưa kiểm soát được.

Ví dụ mẫu bảng ghi kết quả:

| Trường | Giá trị |
|---|---|
| Scenario | Warm incremental build |
| Revision | `abc1234` |
| Task request | `test` |
| Gradle/JDK | `Gradle 8.x / JDK 21` |
| Daemon | Reused |
| Dependency cache | Warm |
| Task outputs | Baseline đã tạo |
| Configuration cache | Reused |
| Build cache | Disabled |
| Input change | Một file Java trong `:service` |
| Iterations | 10 (2 warm-up, 8 measured) |
| Result | Median và range của 8 lần đo |
| Task outcomes | `compileJava`: SUCCESS; các task không liên quan: UP-TO-DATE; ... |

Các giá trị trong bảng là chỗ điền dữ liệu thực tế, không phải mặc định bắt buộc. Không nên ghi “warm build: 5 giây” mà không nói task nào chạy, cache nào được dùng và input có thay đổi không.

## 20. Nguyên tắc chọn scenario theo mục tiêu

Không phải lúc nào cũng cần đo tất cả loại build. Chọn scenario theo trải nghiệm cần cải thiện:

- **Máy developer mới:** first build với Gradle User Home mới, dependency cache lạnh.
- **CI runner ephemeral:** clean execution có dependency cache/mirror hoặc remote build cache theo cấu hình CI thực tế.
- **Developer chạy lại build sau khi không sửa gì:** warm no-change với daemon và configuration cache được reuse.
- **Developer chỉnh một file rồi chạy test:** warm incremental build với input change có kiểm soát.
- **CI chia sẻ output giữa runner:** remote build cache restore.
- **Build nhiều project và plugin:** configuration cache store/reuse và thời gian configuration.
- **Tác vụ compile/test nặng:** clean execution và task execution profile.

Khi tối ưu, hãy ưu tiên scenario đại diện cho cách build được dùng thường xuyên và tác động kinh doanh lớn. Một cải thiện lớn ở first build có thể không giúp developer nếu vòng lặp incremental mới là chi phí chính; ngược lại, tối ưu warm no-op không giúp nhiều nếu CI luôn chạy trong workspace mới và không có cache.

## 21. Nguyên tắc cần nhớ

- “Cold” và “warm” là mô tả trạng thái; luôn ghi rõ cache/process nào lạnh hoặc ấm.
- `clean` xóa build outputs trong phạm vi task clean, không xóa dependency cache hoặc mọi Gradle cache.
- `--no-build-cache`, `--no-configuration-cache`, `--rerun-tasks`, `--refresh-dependencies` và `--no-daemon` tác động đến các cơ chế khác nhau.
- Warm no-change build thường đo chi phí kiểm tra trạng thái/configuration; nó không đo compile/test đầy đủ nếu task đều `UP-TO-DATE`.
- Warm incremental build phải bắt đầu từ baseline giống nhau và thay đổi input có kiểm soát.
- Build cache restore (`FROM-CACHE`) khác với output local up-to-date (`UP-TO-DATE`).
- Configuration cache, dependency cache, build cache, task history và OS filesystem cache không phải một loại cache duy nhất.
- So sánh công bằng cần cùng source, task request, JDK, Gradle, máy, network và cache state.
- Chạy nhiều iteration, tách warm-up khỏi phép đo và báo median cùng độ phân tán.
- Luôn xem task outcomes để chắc chắn các build thực hiện cùng công việc.
- Không hy sinh test hoặc artifact correctness để có thời gian build thấp hơn.

Build lạnh và build ấm đại diện cho những trạng thái sử dụng khác nhau. Muốn benchmark Gradle có ý nghĩa, cần định nghĩa trạng thái daemon, dependency cache, task outputs, configuration cache, build cache và môi trường filesystem/network trước khi chạy. Sau đó chọn scenario phù hợp, giữ các điều kiện còn lại giống nhau, đo nhiều lần và kiểm tra task outcomes. Một báo cáo tốt không chỉ đưa ra số giây mà còn giải thích Gradle đã thực hiện hoặc bỏ qua công việc nào, vì sao kết quả có thể tái lập và giới hạn nào còn ảnh hưởng đến phép đo.
