# Điều kiện tương thích của archive hoặc cache với JDK, ứng dụng và môi trường

## Mục tiêu học tập

Những kỹ thuật **khởi động nhanh JVM** thường chuyển một phần công việc từ lúc chạy ứng dụng sang một bước chuẩn bị trước: tạo **CDS/AppCDS archive**, ghi một dạng cache, hoặc đóng gói dữ liệu đã phân tích để một lần chạy sau tái sử dụng. Điều đó làm nảy sinh câu hỏi quan trọng hơn việc “file cache có tồn tại hay không”:

> **File archive/cache được sinh cho JVM nào, ứng dụng nào và môi trường nào? Khi nào JVM thực sự được phép tái sử dụng nó, khi nào phải bỏ qua hoặc tạo lại?**

Trên **HotSpot Java 17**, ví dụ thực tế và có tài liệu chính thức rõ ràng nhất là **Class Data Sharing (CDS) / Application Class-Data Sharing (AppCDS)** với file `.jsa`. Archive này có thể tăng tốc class loading và giảm một phần memory footprint, nhưng **không phải một file Java chuẩn có thể chạy ở mọi JDK, mọi OS, mọi phiên bản ứng dụng**. Việc JVM từ chối archive không có nghĩa Java bytecode trở nên sai; trong nhiều cấu hình, JVM có thể khởi động theo đường không dùng archive, với hiệu năng khác.

Bài học giúp bạn:

1. Phân biệt **CDS archive**, **JIT Code Cache**, **cache của framework** và **snapshot/cache theo sản phẩm khác** — chúng không có cùng contract tương thích.
2. Nắm **những điều kiện JDK build, classpath/JAR, module path, class loader và cấu hình JVM** ảnh hưởng khả năng tái sử dụng archive Java 17.
3. Hiểu **base archive và dynamic top archive**: quan hệ phụ thuộc và vì sao không thể tùy tiện ghép file.
4. Biết **kiểm chứng bằng CDS/class-load logs**, kiểm thử trường hợp cấu hình thay đổi và chọn fallback/fail-fast hợp lý.
5. Tạo **lab Java 17 runnable** với JAR, static archive, dynamic archive và bộ kiểm tra tương thích cơ bản cho pipeline.
6. Không đánh đồng “ứng dụng in đúng kết quả” với “CDS đã hoạt động” hoặc “có archive” với “startup nhanh hơn”.

**Phạm vi:** JDK/HotSpot **17** và cách đánh giá các loại cache khởi động liên quan. Những tính năng AOT cache ở các JDK mới hơn hoặc snapshot của runtime/framework cụ thể có thể có quy tắc riêng; **không áp đặt option/cơ chế của phiên bản mới lên Java 17**.

---

## 1. Archive tương thích nghĩa là gì?

Một Java application có thể chạy bình thường mà không cần archive. Tương thích của một archive là chuyện khác: JVM cần tin rằng **dữ liệu đã được chuẩn bị trước vẫn mô tả đúng những classes và runtime assumptions ở lần chạy hiện tại**.

```text
                 BUILD / PREPARE
      JDK image + app JARs + JVM options + environment
                         │
                         ▼
               Create CDS archive
                    app.jsa
                         │
               deploy / restart
                         ▼
                  RUNTIME CHECKS
      JVM build, OS/arch, base archive, JAR identities,
       classpath/module configuration, relevant VM options
                         │
               ┌─────────┴─────────┐
               │                   │
           compatible         incompatible
               │                   │
               ▼                   ▼
       Map/reuse archive     Reject/skip/error
               │                   │
               ▼                   ▼
         Java semantics       Java semantics
         remain correct       must remain correct
```

Khi runtime xác nhận archive phù hợp, nó có thể ánh xạ dữ liệu class đã chuẩn bị vào địa chỉ bộ nhớ được phép và giảm công việc load/parse/verify/link tương ứng. Tính tương thích phụ thuộc **định dạng VM nội bộ** và quan hệ với đầu vào ban đầu.

Nếu archive không dùng được, phải tách hai câu hỏi:

- **Khả năng khởi động:** VM sẽ tự fallback hay dừng khởi động? Phụ thuộc `-Xshare` mode và loại lỗi.
- **Lợi ích hiệu năng:** có class dữ liệu ứng dụng nào thực sự được chia sẻ? Phải xem log, không suy từ file có sẵn.

### 1.1. Không phải mọi thay đổi môi trường đều có hậu quả giống nhau

| Thay đổi | Với CDS/AppCDS Java 17 | Tư duy kiểm tra |
| --- | --- | --- |
| Thay **JDK build/vendor/patch** | Archive có thể không tương thích | Tạo lại và xác minh |
| Đổi **JAR bytecode/nội dung** | Archive có thể bị từ chối | Gắn archive với artifact digest |
| Đổi **thứ tự classpath** | Có thể đổi class resolution, vi phạm điều kiện | Giữ classpath nhất quán |
| Runtime classpath thêm **JAR cuối danh sách** | Có điều kiện prefix được tài liệu cho phép | Xác minh lớp nào thực sự share |
| Runtime classpath bỏ/sắp xếp lại JAR | Có nguy cơ không dùng được | So chi tiết dump/runtime |
| Đổi module path | Có quy tắc riêng, không giống prefix classpath | Kiểm tra module JARs và logs |
| Thêm **`--patch-module`** | Oracle JDK 17 nói CDS bị vô hiệu | Đừng kỳ vọng dùng archive |
| Đổi OS/CPU architecture | Định dạng VM/memory mapping phụ thuộc nền tảng | Build archive trên đúng target runtime |
| Đổi hostname hoặc business config thuần dữ liệu | Không tự kết luận làm mất CDS | Kiểm tra liệu nó có đổi class-loading behavior không |
| Đổi heap size/GC option | Một số VM options ảnh hưởng compatibility; không phải mọi flag đều gây lỗi | Dùng logs/negative tests theo cấu hình thật |
| Đổi archive filename/path | Có thể ảnh hưởng tìm file và dependency của dynamic layer | Verify đường dẫn/base mapping |
| Chạy nhiều processes cùng file archive hợp lệ | Có khả năng chia sẻ read-only pages | So startup và PSS/USS, không cộng RSS mù |

**Bài học quan trọng:** archive không phải “dùng được hoặc không” dựa trên duy nhất `java -version`. Một bản Java 17 giống số phiên bản vẫn có thể khác vendor/build/VM flags/arch hoặc classpath.

## 2. Phân biệt các “archive” và “cache” có thể bị gọi chung

| Loại | Nội dung chủ yếu | Thời gian sống | Bảo đảm tái sử dụng giữa JVM runs? |
| --- | --- | --- | --- |
| **Default CDS archive** | Dữ liệu các lớp nền tảng đã được JDK chuẩn bị | File đi kèm JDK image | Có khi compatible với chính runtime image đó |
| **Static AppCDS archive** | Class metadata theo class list và build/runtime inputs | File `.jsa` do bước dump tạo | Có với JDK/classpath/VM settings phù hợp |
| **Dynamic CDS top archive** | Class metadata được ghi từ một lần chạy, trên một base archive | File `.jsa` bổ sung | Có khi top **và base** tương thích |
| **HotSpot JIT Code Cache** | Machine code do C1/C2 biên dịch lúc JVM chạy | Bộ nhớ nội bộ process | **Không mặc định** là persistent cache file tái sử dụng giữa Java 17 processes |
| **OS page cache** | Các pages file đã được OS đọc | Do kernel quản lý | Có thể giúp cold/warm startup, không do Java `SharedArchiveFile` định nghĩa |
| **Framework cache** | Metadata, indexes, generated config, templates, transformed data | Tùy framework | Phải theo contract/version/checksum của framework đó |
| **Native-image / snapshot của sản phẩm khác** | Native binary hoặc serialized runtime snapshot theo công cụ | Build/runtime artifact riêng | Không theo quy tắc CDS `.jsa`, có compatibility rules riêng |

**Không được đồng nhất:** nếu app startup nhanh hơn ở lần thứ hai, nguyên nhân có thể là OS page cache đã ấm, không phải AppCDS archive được dùng. Ngược lại, JIT Code Cache trong một process đã warm-up không phải file có thể copy sang process khác bằng `-XX:SharedArchiveFile`.

### 2.1. Dữ liệu về class khác dữ liệu của object

CDS/AppCDS không phải heap dump. Nó không “đóng băng” trạng thái mutable static fields, session data, in-memory caches, database connections hay business objects để process mới tiếp tục tại cùng state.

```text
CDS archive:
  reusable class-related metadata phù hợp

Không phải:
  Java object heap snapshot
  static field values tại lúc dump
  JIT code/CPU register snapshot
  open sockets và thread stacks
  token/session/application secrets
```

Nếu sản phẩm ngoài HotSpot hỗ trợ một cơ chế **checkpoint/restore**, nó cần tính tương thích riêng cho OS/kernel, filesystem, PID/network, clock, encryption secrets, JVM state và warm-up; **không dùng tài liệu CDS để kết luận nó cũng tương thích**.

## 3. Điều kiện JDK và VM build

CDS archive lưu cấu trúc dữ liệu VM được tối ưu cho **một cách biểu diễn nội bộ cụ thể**. Vì vậy nó không phải một định dạng portable như JAR hoặc class file.

### 3.1. Cùng “Java 17” chưa đủ

Xét các cách thay runtime:

```text
Temurin JDK 17 build A  → Oracle JDK 17 build B
OpenJDK 17.0.8         → OpenJDK 17.0.9
Linux x86_64           → Linux aarch64
Windows                → Linux
JDK 17                 → JDK 21
```

Không giả định archive `.jsa` giữ nguyên khả năng sử dụng trong những thay đổi trên. Compatibility check cụ thể thuộc HotSpot implementation; quá trình build JDK có thể đổi metadata layout. **Đóng gói archive cùng JDK image dùng để chạy và tạo lại archive sau thay đổi JDK** là lựa chọn vận hành an toàn.

Trong môi trường container, `image:tag` có thể trỏ tới image mới sau khi repull. Do đó nếu cần reproduce, pin **image digest** (và ghi `java -version`), không chỉ tên tag.

### 3.2. JDK home và default archive

Java 17 thường có **default CDS archive** đi kèm distribution, chẳng hạn `$JAVA_HOME/lib/server/classes.jsa` trên Linux/macOS theo một số cách đóng gói, hoặc đường dẫn tương đương dưới JDK home trên Windows. Đường dẫn chính xác phụ thuộc JDK image/vendor/platform.

**Không tự tải file `classes.jsa` từ JDK khác về chép vào JDK hiện tại**. Default archive thuộc bộ cài và tương thích với runtime đã tạo nó; thay thủ công bằng binary từ nguồn khác có thể bị từ chối hoặc tạo rủi ro supply-chain.

### 3.3. Class-file version không phải archive-file version

JVM có thể chạy class file `major version 61` của Java 17, nhưng một CDS archive đã tạo bằng một bản JDK khác vẫn có thể không compatible. Lý do:

- **Class file** có định dạng do JVMS quy định, có luật phiên bản và verification.
- **CDS archive** là dữ liệu triển khai nội bộ của HotSpot, không được đặc tả như một portable Java SE artifact.

`javac --release 17` bảo đảm đầu ra class/API target phù hợp Java 17 trong phạm vi compiler, **không đảm bảo một `.jsa` sinh từ JDK build A có thể map bằng JDK build B**.

### 3.4. Một số VM flags ảnh hưởng khả năng map archive

CDS có thể yêu cầu những giả định về data layout, runtime modules, compressed references, heap/memory reservation và VM features. Một số flags/điều kiện có thể khiến archive không dùng được hoặc chỉ một phần khả dụng.

Tránh lập một danh sách ngắn “5 flags chắc chắn disable CDS trong mọi HotSpot Java 17 build” nếu tài liệu không bảo đảm như vậy. Cách đúng:

1. Ghi **toàn bộ effective launcher JVM flags** ở bước tạo archive.
2. Chạy smoke test bằng **cấu hình production thật**, không chỉ cấu hình build.
3. Dùng `-Xlog:cds=info` / `-Xlog:cds=debug` để xem lý do skip/reject.
4. Nếu nghi ngờ option cụ thể, làm A/B test đổi một option rồi quan sát.

**Riêng Java 17 có tài liệu nêu rõ** `--upgrade-module-path`, `--patch-module` hoặc `--limit-modules` vô hiệu CDS; không suy điều này tự động áp dụng cho mọi module-related option khác.

## 4. Điều kiện ứng dụng: JAR content, classpath và thứ tự

**AppCDS static** và **dynamic CDS** đều có ràng buộc quan trọng với class-loading inputs. Archive chỉ có ích khi các classes được load ở runtime có định danh/code/source phù hợp với lúc archive được tạo.

### 4.1. Classpath dùng khi dump và khi chạy lại

Tài liệu Oracle JDK 17 quy định:

> **Classpath lúc tạo archive phải giống hoặc là prefix của classpath lúc runtime.**

Ví dụ:

```text
Tạo archive:
  -cp core.jar:service.jar

Runtime:
  -cp core.jar:service.jar
  → danh sách giống, điều kiện classpath đạt nếu các kiểm tra khác đều đạt

Runtime:
  -cp core.jar:service.jar:optional.jar
  → archive classpath là prefix, có thể đạt điều kiện này

Runtime:
  -cp service.jar:core.jar
  → đổi thứ tự, không còn cùng prefix

Runtime:
  -cp core.jar
  → thiếu thành phần từng dùng khi dump, không đạt điều kiện này
```

Trên **Windows**, phần tử classpath phân tách bởi `;`, còn trên Linux/macOS thường dùng `:`. Đừng nhầm dấu phân tách classpath với định dạng file JAR hoặc dấu phân tách **base/top archives**.

**Quan trọng:** “prefix được phép” không có nghĩa JAR cuối thêm vào luôn vô hại. Nếu JAR mới thay đổi class resolution/loader behavior, VM vẫn phải bảo đảm correctness và class-sharing eligibility. Chỉ khi verification/logs xác nhận thì mới coi archive hữu ích.

### 4.2. Sửa JAR sau khi dump

Oracle JDK 17 nêu rằng **CDS archive không thể được nạp nếu JAR trên class path hoặc module path bị sửa sau khi tạo archive** trong phạm vi kiểm tra liên quan.

Những thao tác có thể gây invalidation:

- Build lại application JAR với class bytes mới.
- Nâng version thư viện dependency.
- Thay JAR trong `lib/` nhưng giữ nguyên filename.
- Repackage JAR thay đổi manifest, entries hoặc metadata liên quan.
- Copy file mới lên đúng path sau khi archive được tạo.

**Đừng chỉ hash tên file.** Dùng content digest, release manifest hoặc artifact IDs để gắn archive với đúng binary inputs. Có trường hợp rebuild “cùng source code” vẫn sinh bytes/metadata khác nên không nên hứa archive sẽ hoạt động.

### 4.3. Đường dẫn JARs và reproducible deployment

Đường dẫn tuyệt đối, tương đối, symlink, current working directory và cách launcher mở JARs đều có thể gây khác biệt:

```text
Build:
  java -cp /app/lib/core.jar:/app/myapp.jar ...

Run:
  java -cp ./lib/core.jar:./myapp.jar ...
```

Đừng tự khẳng định hai cách viết tương đương cho mọi CDS compatibility check. JVM có các điều kiện xác minh source path/classpath; hãy **giữ startup commands, cwd và layout ổn định**, nhất là trong container images.

Nếu phải relocate ứng dụng, tái tạo archive ở layout mới hoặc ít nhất chạy xác minh `cds`/`class+load` trên target layout. Không giải quyết “file archive tồn tại mà không dùng” bằng cách tắt mọi kiểm tra.

### 4.4. Non-empty directories không giống JAR files

Theo Oracle Java 17 **CDS restriction**:

- Classpath (`-classpath` và `-Xbootclasspath/a`) không được chứa **non-empty directories** khi tạo/sử dụng CDS archive theo các ràng buộc được tài liệu mô tả.
- Module path không được chứa non-empty directories; chỉ **modular JARs** được hỗ trợ cho archiving trong điều kiện nói tới.
- Exploded modules không được hỗ trợ cho module path trong quy trình CDS tương ứng.

```bash
# Chạy ứng dụng Java bình thường có thể được:
java -cp out MyMain

# Nhưng để tạo AppCDS archive Java 17 tin cậy, dùng packaged JAR:
java -cp myapp.jar MyMain
```

Hai lệnh này minh họa **class-loading packaging**; class `MyMain` phải được cung cấp tương ứng. Không có nghĩa Java launcher cấm dùng thư mục `out` nói chung; nó chỉ **không đáp ứng một số điều kiện CDS archive**.

### 4.5. Wildcard và dependency resolution

Các launcher có thể cho `-cp "lib/*"`, nhưng thứ tự JARs thực tế và bộ dependencies cần được xác nhận thay vì coi wildcard là một danh sách ổn định theo ý developer. Nếu bộ JARs thay đổi, điều kiện AppCDS và khả năng class resolution thay đổi.

Khuyến nghị:

- Ghi effective classpath khi tạo archive.
- Giữ thứ tự/phạm vi JAR nhất quán giữa dump/run.
- Dùng immutable build artifacts trong image/container.
- Tránh cập nhật hot-swap JAR dưới đường dẫn đang dùng cho archive.
- Regenerate archive khi thay dependency graph.

## 5. Module path: quy tắc khác với classpath

Java 9+ có module system; ứng dụng modular có thể được khởi chạy bằng `--module-path` và `-m`. Với Java 17, CDS hỗ trợ các **modular JARs** phù hợp, nhưng không phải mọi kiểu module placement đều đủ điều kiện.

**Ba nguyên tắc:**

1. Classpath có quy tắc **same-or-prefix** khi dump vs runtime theo docs.
2. Oracle nói **không có cùng yêu cầu prefix cho module path**.
3. Tuy nhiên JARs trên module path vẫn phải còn phù hợp và **không bị sửa** sau khi archive tạo; những module options đặc biệt có thể vô hiệu CDS.

```bash
# Ví dụ launcher modular (package/module artifacts phải tồn tại):
java --module-path mods -m com.example.app/com.example.app.Main
```

Đây là **snippet cú pháp launcher**, không phải một runnable app độc lập vì không cung cấp module descriptor/JARs. Không suy `--module-path mods` đủ điều kiện archiving nếu `mods` là exploded directory thay vì chứa modular JARs đúng điều kiện.

### 5.1. Những module-related options vô hiệu CDS trong JDK 17

Oracle Java SE 17 launcher manual nêu rõ ba nhóm:

```bash
--upgrade-module-path
--patch-module
--limit-modules
```

Nếu các options này xuất hiện, CDS **bị vô hiệu**. Khi dùng chúng để tạo archive, VM có thể báo lỗi dump; khi dùng trong runtime, JVM chạy không load CDS archives theo mô tả của tài liệu.

Đừng dùng `-Xshare:on` để “ép CDS bất chấp module patching”: strict mode không làm không tương thích trở nên an toàn.

### 5.2. Custom class loaders, reflection và plugin systems

Frameworks có custom class loaders, proxies, generated classes, nested JARs hoặc runtime weaving có thêm điều kiện archive eligibility. Java 17 CDS có hỗ trợ một số class loading qua custom class loaders theo quy tắc nhất định, nhưng **không bảo đảm mọi dynamic proxy/generated class luôn được archive**.

Ví dụ những thay đổi cần xem:

- Plugin class loader loads JARs ở startup A khác startup B.
- Framework version mới tạo classes có tên/nội dung khác.
- Bytecode instrumentation agent thay classes trước/đang load.
- Application bật/tắt feature flags làm bộ classes được nạp khác.
- “Fat JAR” launcher mở nested JARs khác với flat classpath thông thường.

**Quy trình:** dùng đúng startup script của framework, warm-up representative code paths, bật `-Xlog:class+load=info` và kiểm tra **classes của chính ứng dụng** có `source: shared objects file` hay không. Thấy một core class được share không chứng minh cả framework đã share.

## 6. Archive tĩnh, archive động và điều kiện base–top

Trong HotSpot Java 17, có thể cấu hình **tối đa hai tầng CDS archive** theo Java launcher docs:

```text
           Static/base archive
                   │
                   ▼
           Dynamic/top archive
                   │
                   ▼
          Runtime maps base + top
```

Dạng tổng quát:

```text
-XX:SharedArchiveFile=<static_archive>:<dynamic_archive>
```

Ở Windows, dùng dấu phân tách `;` thay cho `:`. Nếu chỉ có một archive file, VM xác định dạng/tầng tương ứng qua metadata của file; dynamic archive lưu thông tin về base archive thích hợp, nên có thể chỉ cần `-XX:SharedArchiveFile=top.jsa` khi default/custom base khớp.

### 6.1. Static archive

Quy trình thông thường:

1. Chạy ứng dụng để ghi `app.classlist`.
2. Tạo `app-static.jsa` bằng `-Xshare:dump` + `SharedClassListFile`.
3. Chạy lại bằng `SharedArchiveFile`.

Tính tương thích cần xét cả JDK build, classpath/other options và file JARs. Có archive tĩnh không đồng nghĩa “không cần input JAR” khi runtime.

### 6.2. Dynamic archive

Quy trình thông thường:

1. Có base CDS archive phù hợp.
2. Chạy ứng dụng với `-XX:ArchiveClassesAtExit=app-dynamic.jsa`.
3. JVM ghi dynamic **top** archive khi exit phù hợp.
4. Lần chạy sau dùng `-XX:SharedArchiveFile=app-dynamic.jsa` hoặc chỉ định base/top.

**Dynamic archive không tồn tại độc lập với base compatibility assumptions**. Nếu thay default CDS archive hoặc đổi JDK build, dynamic top có thể bị từ chối. Không thể copy mỗi top sang image khác rồi cho rằng nó tự mang theo mọi dữ liệu lớp nền.

### 6.3. “Dynamic” không phải tự sửa cache trong mọi lần chạy

`ArchiveClassesAtExit` ghi ở **cuối một lần chạy**. Nó không có nghĩa:

- Khi một class mới được load, file `.jsa` được cập nhật ngay.
- File cũ luôn tự đồng bộ nếu JAR thay đổi.
- JVM tự xóa mọi archive không tương thích.
- Mọi bản HotSpot Java 17 đã có một `AutoCreateSharedArchive` behavior tương tự các JDK mới.

Nếu thay ứng dụng, cần **tái tạo archive** theo quy trình đúng, không đợi cache cũ tự “cập nhật”.

### 6.4. Trường hợp đổi base mà quên top

```text
Run A:
  JDK image A → base-A.jsa → app-top-A.jsa

Run B:
  JDK image B → base-B.jsa + app-top-A.jsa
                                 │
                                 ▼
                      compatibility không được đảm bảo
```

Một chiến lược release tốt là xuất bản **JDK image + ứng dụng JARs + custom/base/top archives** thành cùng một versioned unit. Đổi bất kỳ thành phần quan trọng nào → regenerate và test ở target.

## 7. AppCDS không dùng chung quy tắc với JIT Code Cache

HotSpot Java 17 còn có thuật ngữ **Code Cache**, là vùng memory giữ compiled machine code mà C1/C2 sinh trong runtime. Dù tên có “cache”, nó khác CDS:

- JIT compiled code thường phụ thuộc CPU instructions, receiver type profiles, compiler decisions, VM runtime addresses và các giả định về class loading.
- Nó được quản lý bởi JVM process; không có một cơ chế Java SE 17 chuẩn để dump toàn bộ JIT Code Cache thành `jit.jsa` rồi mang đi `SharedArchiveFile`.
- `-XX:ReservedCodeCacheSize` điều khiển capacity code cache (theo HotSpot), **không tự tạo persistent disk archive**.
- Code cache có thể bị thu dọn/reclaim trong quá trình runtime khi compiled code không còn dùng.
- Với warm-up trong cùng process, JIT đã compile methods và lần gọi sau chạy nhanh hơn; đó **không phải** bằng chứng về CDS compatibility giữa hai processes.

```text
CDS .jsa:          disk artifact → mapping class data across JVM processes
JIT Code Cache:    in-process machine code → JIT runtime optimization
OS page cache:     kernel-managed file pages → may affect disk I/O/startup
Framework cache:   provider-defined data → version/config validity rules
```

**Lưu ý:** Các cơ chế profile-guided optimization hoặc AOT compilation có ở những JDK/VM/products khác không biến mặc định HotSpot JDK 17 thành “có AOT cache portable”. Nếu dự án thực sự dùng một accelerator riêng, cần đọc documentation của **phiên bản chính xác** đó và định nghĩa compatibility riêng, không áp dụng máy móc bảng CDS.

## 8. Cache của framework: phải định nghĩa cache key và invalidation

Một framework có thể cache generated serializers, JSON schema, classpath scanning indexes, dependency injection metadata hoặc bytecode được sinh ra. Tính hợp lệ có thể phụ thuộc:

- Framework version, serializer/compiler version.
- Tập classes/JARs và content digests.
- Configuration flags, annotations, profiles và active modules.
- Data model/schema version, database mapping.
- Locale/timezone hoặc resource bundles nếu cache chứa dữ liệu phụ thuộc môi trường.
- OS/architecture nếu cache lưu native code hoặc addresses.
- Secrets/tenant-specific config nếu cache giữ dữ liệu nhạy cảm.

Không có quy tắc Java SE phổ quát “framework cache hợp lệ miễn JDK major version giống nhau”.

### 8.1. Định nghĩa compatibility contract cho cache do chính bạn xây

Ví dụ metadata manifest (chỉ là minh họa định dạng dữ liệu, không phải format mà HotSpot tự đọc):

```text
cacheFormatVersion=3
javaVendor=ExampleVendor
javaRuntimeVersion=17.0.x+build
osArch=amd64
appArtifactSha256=...
dependencyGraphSha256=...
configFingerprint=...
serializerVersion=...
generationEpoch=...
```

Một application cache nên có **versioned cache format**, hash hoặc signature của dữ liệu nền, kiểm tra integrity, atomic publication và fallback có thể đo được. Các trường nào quan trọng phụ thuộc chính cache đó; đừng giả định cần lưu hoặc gửi mọi secret ở dạng plaintext trong manifest.

**Đối với CDS archive**, manifest ngoài có thể dùng để quản lý release/CI, nhưng nó **không thay VM internal compatibility checks**.

## 9. Java 17 runnable lab: một JAR cho các phép thử archive

Đây là ứng dụng tối giản có thêm hai nested classes để quan sát class loading. Lưu **`ArchiveCompatibilityDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public final class ArchiveCompatibilityDemo {
    static final class Catalog {
        List<String> items() {
            return List.of("java", "jvm", "cache");
        }
    }

    static final class Formatter {
        String format(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Catalog catalog = new Catalog();
        Formatter formatter = new Formatter();
        List<String> items = catalog.items();

        int count = 0;
        for (String item : items) {
            count += item.length();
        }

        System.out.println("items=" + items.size());
        System.out.println("totalChars=" + count);
        System.out.println("first=" + formatter.format(items.get(0)));
        System.out.println("version=" +
                Runtime.version().feature());
        System.out.println("done");
    }
}
```

**Chuẩn bị bằng JDK 17:**

```bash
mkdir -p out
javac --release 17 -d out ArchiveCompatibilityDemo.java
jar --create --file archive-demo.jar \
    --main-class ArchiveCompatibilityDemo -C out .
```

Lệnh là cú pháp POSIX shell; trên Windows có thể viết các câu lệnh `javac`/`jar` thành một dòng và dùng `mkdir out` theo shell phù hợp.

**Chạy bình thường trên JDK 17:**

```bash
java -cp archive-demo.jar ArchiveCompatibilityDemo
```

**Stdout ứng dụng chính xác trên JDK 17, không bật diagnostic logs:**

```text
items=3
totalChars=12
first=JAVA
version=17
done
```

Bởi vì `"java"` có 4 ký tự, `"jvm"` có 3 ký tự, `"cache"` có 5 ký tự, tổng **12**. `Runtime.version().feature()` bằng **17** trên runtime JDK 17. Nếu cố ý chạy JAR này bằng JDK mới hơn, dòng `version=...` sẽ thay đổi; vì thế ví dụ xác định stdout **trong phạm vi Java 17 đã chỉ định**.

### 9.1. Vì sao biên dịch xong phải đóng gói JAR?

Oracle Java 17 AppCDS restrictions không hỗ trợ non-empty classpath directories trong những trường hợp tạo/dùng archive. Chúng ta đóng gói `archive-demo.jar` để giữ cùng binary input xuyên trial/dump/runtime.

**Không sửa nội dung file JAR giữa bước dump và bước runtime**. Nếu mở `out` rồi chạy `javac` lại nhưng không rebuild JAR thì JAR vẫn cũ; nếu rebuild JAR thì archive cũ có thể không tương thích — cả hai tình huống cần được phân biệt rõ.

## 10. Lab static archive — tạo, chạy, kiểm tra

### 10.1. Trial run tạo class list

```bash
java -Xshare:off \
  -XX:DumpLoadedClassList=archive-demo.classlist \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

Lệnh chạy `main` và ghi **file class list**. Nội dung file phụ thuộc những classes runtime thực sự load. File classlist không phải archive; muốn tạo archive phải có bước tiếp theo.

### 10.2. Tạo static archive

```bash
java -Xshare:dump \
  -XX:SharedClassListFile=archive-demo.classlist \
  -XX:SharedArchiveFile=archive-static.jsa \
  -cp archive-demo.jar
```

Ở chế độ `dump`, JVM tạo file `archive-static.jsa`. Đây **không phải** lần thực thi `ArchiveCompatibilityDemo.main()`, nên không bắt buộc có stdout nghiệp vụ như phần 9.

### 10.3. Chạy lại và xác minh

```bash
java -Xshare:auto \
  -XX:SharedArchiveFile=archive-static.jsa \
  -Xlog:cds=info,class+load=info \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

Ứng dụng **vẫn phải cho kết quả nghiệp vụ tương đương** phần 9. Ngoài ra có các dòng VM logging, có thể bao gồm nguồn nạp lớp kiểu **`source: shared objects file`**. Thời điểm, số lines, addresses, class loading order tùy JDK build, vì vậy **không bịa một transcript logger cố định**.

### 10.4. Baseline không CDS

```bash
java -Xshare:off -cp archive-demo.jar ArchiveCompatibilityDemo
```

Đây là phép đối chiếu: ứng dụng chạy đúng Java semantics nhưng không sử dụng CDS. Nếu so thời gian startup, chạy nhiều lần, cùng JDK/cpu/heap/cwd/JARs và xem warm filesystem page cache.

### 10.5. Điều gì chứng minh tương thích?

- File archive tồn tại và không bị lỗi quyền đọc.
- Runtime log cho thấy CDS mapping thành công.
- Một số **application classes** trong log có `source: shared objects file`, không chỉ lớp `java.base`.
- Không có thông báo reject/skip archive liên quan.
- Output nghiệp vụ vẫn đúng.
- Kết quả có thể lặp lại ở môi trường mục tiêu.

Chỉ có exit code 0 và `done` **không đủ chứng minh** archive được dùng.

## 11. Lab dynamic archive — base/top và compatibility

### 11.1. Tạo dynamic top archive khi JVM thoát

```bash
java -Xshare:auto \
  -XX:ArchiveClassesAtExit=archive-dynamic.jsa \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

Nếu JVM có base archive phù hợp và shutdown/dump thành công, file `archive-dynamic.jsa` sẽ được tạo. Nó bổ sung classes eligible đã nạp nhưng chưa có ở base; nó **không** chứa một bản sao toàn bộ heap.

### 11.2. Sử dụng dynamic archive

```bash
java -Xshare:auto \
  -XX:SharedArchiveFile=archive-dynamic.jsa \
  -Xlog:cds=info,class+load=info \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

HotSpot sử dụng thông tin về base archive liên quan từ dynamic archive. Nếu base đổi/không còn map phù hợp, dynamic top có thể không được dùng. Không copy top sang JDK khác rồi suy rằng nó độc lập.

### 11.3. Tùy chọn ghi cả base và top

Nếu có một custom static base archive phù hợp, có thể thử:

```bash
# Khi đã có custom base và đã tạo top trên base này:
java -XX:SharedArchiveFile=base.jsa:top.jsa \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

Dấu `:` là delimiter trên POSIX; Windows dùng `;`. Đây là **snippet minh họa** vì `base.jsa`/`top.jsa` cần được tạo từ đúng JDK và ứng dụng trước đó.

**Không nối binary files bằng `cat base.jsa top.jsa > both.jsa`**. Cấu trúc header/tầng lớp do HotSpot quản lý; lựa chọn cấu hình đúng là `SharedArchiveFile`.

## 12. Thực hành kiểm tra tình huống không tương thích

Những thí nghiệm sau nên thực hiện trong **workspace lab cách ly**, không sửa JAR production để thử:

### Tình huống A — Thay app JAR sau dump

1. Tạo `archive-static.jsa` với JAR version A.
2. Cố ý sửa source rồi build JAR version B vào cùng path.
3. Chạy với archive A và bật `-Xlog:cds=debug,class+load=info`.
4. Ghi exit code, CDS reason, classes thực sự được load.
5. Tạo lại archive với version B, verify lần nữa.

**Kỳ vọng có thể kiểm chứng:** file archive cũ không được tin cậy nếu JAR nguồn đã đổi theo CDS checks. **Không khẳng định mọi VM build sẽ in chính xác cùng câu lỗi**, và không dùng strict mode trong production.

### Tình huống B — Đổi thứ tự JARs

```text
Archive creation classpath:
  lib/a.jar:lib/b.jar

Runtime classpath:
  lib/b.jar:lib/a.jar
```

Classpath lúc runtime không còn cùng thứ tự/prefix. Điều này có thể thay class resolution. Không ép JVM dùng archive bằng cách đổi tên file; chuẩn hóa thứ tự JARs và tạo lại archive nếu startup classpath của production khác.

### Tình huống C — Đổi JDK patch/vendor

- Archive trên build X.
- Khởi động với JDK build Y.
- Quan sát logs/exit code.
- Regenerate archive dưới build Y.
- Verify dưới chính build Y.

Không có quy tắc “major version 17 giống nhau thì file `.jsa` chắc chắn portable”. Dùng build-specific artifact metadata trong CI.

### Tình huống D — Thêm `--patch-module`

Khi một command line chứa `--patch-module` theo cách có hiệu lực, Oracle JDK 17 docs nói **CDS bị disable**. Đây là negative test rõ ràng để dạy sự khác nhau giữa JDK module configuration và binary archive:

```text
CDS enabled app run ≠ app run có --patch-module
```

Đừng thử nó bằng cách đưa một module path giả lập để rồi quy kết mọi lỗi launch là do CDS; chỉ test khi bạn có modular application đúng và patching cần thiết.

### Tình huống E — Default base bị thay

Dynamic top tạo trên default base của JDK X. Nếu base archive của JDK Y khác, dynamic top có thể không compatible. Tạo lại top với chính base của runtime Y, không tái sử dụng bằng niềm tin vào tên file giống nhau.

## 13. `-Xshare:off`, `auto` và `on` ảnh hưởng fallback

| Mode | Ý định | Khi archive không dùng được |
| --- | --- | --- |
| `-Xshare:off` | Không dùng CDS | JVM vẫn chạy theo đường không dùng archive nếu không có lỗi khác |
| `-Xshare:auto` | Dùng CDS khi đủ điều kiện | Thường có thể bỏ qua archive không phù hợp theo chính sách; phải xem loại lỗi và log |
| `-Xshare:on` | Yêu cầu CDS bằng strict mode | Nếu không dùng được archive có thể **dừng khởi động với lỗi** |
| `-Xshare:dump` | Tạo static archive | Lỗi dump khiến bước chuẩn bị thất bại; không phải application startup |

**Không xem `-Xshare:on` là “bật tối ưu mạnh hơn”.** Nó chủ yếu đặt kỳ vọng nghiêm ngặt rằng CDS phải khả dụng. Oracle Java 17 CDS docs nói `on` **dành cho thử nghiệm** và không nên dùng trong production nếu môi trường có thể đổi JDK/options.

### 13.1. Production fallback là một quyết định vận hành

Một service phải ưu tiên startup availability có thể dùng `-Xshare:auto` cùng metrics để phát hiện archive bị bỏ qua, sau đó rebuild ở release tiếp theo. Một CI preflight cần phát hiện lỗi sớm có thể chạy một **smoke test strict** trong môi trường kiểm soát.

Tránh hai cực đoan:

- **Silent ignore:** “App chạy được nên AppCDS chắc ổn”; có thể âm thầm mất lợi ích startup.
- **Strict everywhere:** “Mọi JVM process buộc phải dùng CDS bằng `on`”; có thể biến một archive mismatch thành outage.

Thiết kế tốt: **fail-fast trong CI, availability-conscious trong production, alert khi expected sharing không còn**.

## 14. Đọc logs để phân biệt mismatch với miss vì chưa có class

Các tùy chọn HotSpot Java 17 quan trọng:

```bash
-Xlog:cds=info
-Xlog:cds=debug
-Xlog:class+load=info
-Xlog:cds=debug,class+load=info
```

**`cds` logs** cho thấy các hoạt động open/map/validation của archive. **`class+load` logs** cho nguồn của từng class khi load.

Một ví dụ dòng **minh họa**, không phải transcript của lab:

```text
[info][class,load] ... source: shared objects file
[info][class,load] ... source: file:/app/archive-demo.jar
```

Cách đọc:

- `source: shared objects file` cho một class: class đó được load từ shared archive.
- `source: file:/...jar`: ở lần chạy ấy JVM đọc từ JAR, không chứng minh cả archive không được dùng.
- Log báo archive skipped/incompatible: phải xử lý lý do trước khi kỳ vọng startup benefit.
- Chỉ thấy JDK core classes từ shared archive: **default CDS có thể hoạt động**, còn AppCDS classes có thể chưa được share.
- Một class chưa được nạp trong workload thì không có evidence để kết luận nó được share, dù class file có trong JAR.

### 14.1. Kiểm tra lớp ứng dụng, không chỉ JVM classes

Ví dụ sau có nested classes:

```text
ArchiveCompatibilityDemo
ArchiveCompatibilityDemo$Catalog
ArchiveCompatibilityDemo$Formatter
```

Trong `class+load` log của lần chạy, tìm các class này và nguồn của chúng. Không suy từ các classes `java.lang.String`, `java.util.List` đã share rằng AppCDS custom archive đã làm việc.

### 14.2. Kiểm tra sau upgrade, không chỉ sau build

Một archive đã verify tại build machine **chưa chứng minh** nó dùng được trên target container/host vì environment có thể khác. Thêm một **post-deploy smoke test** hoặc startup log inspection có kiểm soát.

Khi runtime phải xử lý lỗi mismatch, ghi lại **JDK/vendor/build, archive ID/checksum, app artifact digest, classpath/module options và CDS log reason**. Những dữ liệu này giúp phân biệt “JDK đổi” và “JAR đổi” thay vì chỉ tìm file missing.

## 15. Cơ chế kiểm tra tương thích cho CI/CD

Một release pipeline có thể theo bước:

```text
    Pin JDK image digest và runtime architecture
                        │
                        ▼
    Build immutable JARs + dependency manifest
                        │
                        ▼
    Record effective classpath/module configuration
                        │
                        ▼
       Tạo static hoặc dynamic CDS archive
                        │
                        ▼
       Ghi metadata/digests của artifact inputs
                        │
                        ▼
      Smoke test trên SAME runtime image/flags
         -Xlog:cds,class+load
                        │
                 ┌──────┴──────┐
                 │             │
             PASS used?      NO / fallback?
                 │             │
                 ▼             ▼
      Package JDK+JAR+JSAs   Regenerate/diagnose
                 │
                 ▼
      Deploy immutable unit + post-deploy verify
                 │
                 ▼
       Monitor startup time + memory footprint
```

### 15.1. Metadata manifest — helper bên ngoài, không phải VM format

Ví dụ thông tin release nên ghi:

```text
runtime.version=17.0.x+build
runtime.vendor=<vendor>
runtime.imageDigest=<digest>
os.arch=<architecture>
archive.type=static-or-dynamic
archive.baseId=<base-id-if-any>
archive.sha256=<sha256>
application.jar.sha256=<sha256>
dependencies.lock.sha256=<sha256>
classpath.signature=<canonicalized-cp-hash>
modulepath.signature=<canonicalized-mp-hash>
required.vm.options=<recorded-keys>
```

Các placeholders chỉ thể hiện **schema minh họa** cho CI, không phải Java program cần compile. **CDS archive không tự đọc file manifest này**: VM vẫn tự kiểm tra những điều kiện nội bộ.

### 15.2. Atomic publication và quyền file

Nên tạo archive ở một **đường dẫn tạm** trong build/job, verify thành công, rồi đổi tên/publish **một lần** theo cơ chế filesystem phù hợp. Tránh để một process đọc file trong khi process khác đang ghi chưa xong.

- Chỉ mount archive có nguồn tin cậy.
- Run user có **quyền đọc archive** và **truy cập các thư mục cha**.
- Khi dump cần **quyền tạo/ghi file** ở destination.
- Đừng dùng cùng một tên `app.jsa` cho nhiều builds đồng thời.
- Có checksum/size sanity check khi đưa artifact qua hệ thống lưu trữ.
- Tránh tự chỉnh binary `.jsa`; format thuộc HotSpot.
- Nếu nhiều runtime processes cùng dùng một archive immutable, giữ file ổn định để OS có thể chia sẻ mapped pages theo điều kiện nền tảng.

## 16. Môi trường triển khai: containers, OS, CPU và storage

### 16.1. Docker/Kubernetes

Một container image có thể chứa JDK, application JARs và archive theo đúng layout:

```text
/app/
  jdk/
  lib/
    app.jar
    dep-a.jar
  cds/
    app.jsa
```

Đây là **sơ đồ deployment**. Khi xây image:

- Chốt **JDK image/build** và architecture trong build stage.
- Nếu build multi-stage, không tạo archive bằng JDK builder khác JDK runtime.
- Giữ JARs/dependencies immutable và paths tương thích.
- Nếu làm multi-arch image, tạo/verify archive cho **từng target architecture**.
- Phân biệt ephemeral writable layer với immutable archive dùng lúc startup.
- Nếu archive được tạo lúc pod shutdown bằng `ArchiveClassesAtExit`, filesystem ephemeral/pod deletion có thể khiến file không tồn tại cho pod tiếp theo; dùng dedicated archive-generation build job hoặc persistent artifact publishing.
- Không dựa vào `SIGKILL` shutdown để archive-at-exit hoàn tất.

### 16.2. CPU instruction set và OS

Machine code lưu trong JIT Code Cache có thể sử dụng CPU instructions riêng. CDS archive không phải JIT compiled code, nhưng vẫn là binary VM artifact và có các assumptions về platform/build; **không giả định archive có thể chuyển từ Linux x86_64 sang Windows/aarch64**.

File paths, separators và permissions cũng khác. Trên Windows, `-XX:SharedArchiveFile=base.jsa;top.jsa` sử dụng `;` làm delimiter. Trên POSIX, dùng `:` như tài liệu Oracle.

### 16.3. Storage, memory mapping và file permissions

CDS cần đọc/map file archive theo khả năng OS/VM. Các vấn đề có thể gồm file missing, permission denied, truncation, mapping constraints hoặc artifact corruption.

Một file có tên `app.jsa` nhưng kích thước 0 byte rõ ràng không phải một archive hữu dụng. Nhưng một file có kích thước lớn và checksum tồn tại **cũng chưa đủ**: JVM phải validate internal contents và khả năng tương thích.

### 16.4. Nhiều JVM processes và shared pages

Một lợi ích của CDS là OS có thể chia sẻ các read-only mapped pages giữa nhiều processes trên cùng host. Tuy vậy, **không bảo đảm** mỗi container/pod đều chia sẻ cùng physical pages nếu filesystem/mount/build khác nhau.

Khi đo memory:

- `RSS` của nhiều processes có thể chứa shared pages và bị đếm trùng khi cộng.
- `PSS` hoặc các metrics tách shared/private (nếu OS hỗ trợ) có ích hơn khi đánh giá lợi ích tổng.
- Heap objects/static mutable states của từng process không trở thành shared business data chỉ nhờ AppCDS.

## 17. Đo “tương thích” và “nhanh hơn” là hai bài kiểm tra khác nhau

**Compatibility test** hỏi:

> Archive có được JVM **chấp nhận và thực sự dùng** không?

**Performance test** hỏi:

> Startup/readiness/memory footprint của ứng dụng có **cải thiện đáng kể và lặp lại** so với baseline không?

Tương thích **không tự bảo đảm** lợi ích đo được. Nếu app rất nhỏ, phần thời gian liên quan class loading có thể không đáng kể so với OS process startup. Ngược lại, một app lớn có nhiều classes startup có thể hưởng lợi hơn.

### 17.1. Chọn chỉ số startup đúng

- JVM process launch → first Java log.
- Process launch → service listen port opened.
- Process launch → readiness check đáp ứng.
- Process launch → first successful business request.

Đo cùng định nghĩa ở mọi cấu hình. Nếu process có lazy initialization, “main đã in done” không nhất thiết là lúc service thực sự sẵn sàng.

### 17.2. So ba trạng thái có ý nghĩa

```bash
# Không dùng CDS:
java -Xshare:off -cp archive-demo.jar ArchiveCompatibilityDemo

# Có default CDS (nếu hợp lệ):
java -Xshare:auto -cp archive-demo.jar ArchiveCompatibilityDemo

# Có AppCDS archive đã được verify:
java -Xshare:auto -XX:SharedArchiveFile=archive-static.jsa \
  -cp archive-demo.jar ArchiveCompatibilityDemo
```

Chạy nhiều lần, đảo thứ tự để hạn chế bias do OS page cache, cố định host load/JDK/CPU quotas và phân tích median/p95 cùng counts. Đừng tuyên bố một cấu hình nhanh hơn X% chỉ từ một lần chạy của demo rất ngắn.

### 17.3. GC và JIT logs có thay cho CDS logs không?

Không. `-Xlog:gc*` tập trung vào GC events, còn `-XX:+PrintCompilation` về JIT compilation. Muốn kiểm tra class có dùng CDS, xem `-Xlog:cds` và `-Xlog:class+load`; sau đó dùng GC/JIT logs khi giải thích các khía cạnh performance khác.

Một câu nói chính xác: **“AppCDS có thể giảm class loading cost; JIT, GC và application initialization vẫn tồn tại.”**

## 18. Những kịch bản lỗi phổ biến và hành động đề xuất

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| JVM báo archive bị từ chối sau nâng JDK | VM build/internal layout đổi | Regenerate trên exact JDK runtime |
| Run vẫn thành công nhưng không thấy class app shared | Default CDS được dùng, AppCDS không match hoặc class chưa eligible | Xem `cds`/`class+load` và classpath |
| Static dump báo liên quan non-empty directory | Archive classpath không dùng JARs phù hợp | Package classes vào JAR |
| Dynamic top không dùng sau đổi image | Base archive dependency mismatch | Tạo lại top trên base của runtime mới |
| Runtime classpath khác build/dump | JAR order/path/content đã thay | Đồng bộ classpath và rebuild archive |
| Module patching có hiệu lực | `--patch-module` vô hiệu CDS theo Java 17 docs | Chấp nhận chạy không CDS hoặc thay thiết kế |
| App chạy với `-Xshare:off` | Cấu hình tắt sharing | Sửa launcher nếu muốn sử dụng archive |
| Strict `-Xshare:on` làm fail startup | Archive không đáp ứng compatibility/availability | Không dùng strict trong production; sửa archive trong CI |
| File archive thiếu trong container | Không copy vào runtime image, mount/path khác | Verify image filesystem/digest |
| File archive không tạo khi shutdown | App bị kill/không dump hoàn tất | Dedicated generation run + graceful exit |
| Startup time không đổi | Classes chưa hưởng lợi hoặc bottleneck khác | Verify class sources và profile startup |
| Chỉ default classes shared | App-specific archive không được dùng/hits thấp | Warm-up đại diện, kiểm tra eligibility |
| Nhiều pod memory không giảm | Không chia thực shared pages, data chủ yếu heap | Đo PSS/USS và deployment file mapping |
| App logic sai sau upgrade | Bug classpath/class loader/deployment, không nên quy tội archive ngay | Chạy `-Xshare:off` đối chiếu + phân tích logs |
| Cache framework sai dữ liệu | Cache key thiếu dependency/config version | Sửa invalidation strategy riêng của framework |

### 18.1. `-Xshare:off` là diagnostic A/B, không phải chữa khỏi mọi lỗi

Nếu JVM khởi động được với `-Xshare:off` nhưng không chạy được với custom archive, đó là manh mối compatibility/option. Nhưng nếu ứng dụng vẫn ném `ClassNotFoundException` hoặc business data lỗi trong cả hai modes, không nên đổ lỗi cho archive.

Giữ log cả hai runs và so effective classpath, JVM version và exceptions.

## 19. Những hiểu lầm cần loại bỏ

1. **“Archive dùng được trên mọi máy có Java 17.”** Sai. VM build/arch/classpath và runtime assumptions có thể khác.
2. **“Java class file portable nên `.jsa` cũng portable.”** Sai. CDS archive là HotSpot-specific binary artifact.
3. **“AppCDS thay thế JAR file.”** Sai. JAR/classpath/resources vẫn cần tương thích.
4. **“Đổi tên JAR là đủ để cache tương thích lại.”** Sai. Tính hợp lệ phụ thuộc nội dung/đường phân giải được kiểm tra.
5. **“Đổi dependency nhưng tên JAR không đổi thì archive chắc còn dùng được.”** Sai.
6. **“Runtime classpath có thể đảo JAR order thoải mái.”** Sai. Order ảnh hưởng class resolution và prefix rule.
7. **“Một classpath directory hoạt động với `java -cp` thì luôn được AppCDS archive.”** Sai. Có ràng buộc non-empty directory.
8. **“Module path phải luôn là prefix giống classpath.”** Sai. Oracle docs phân biệt hai trường hợp.
9. **“`--patch-module` không liên quan CDS.”** Sai. Theo Java 17 docs, nó vô hiệu CDS.
10. **“Archive tĩnh và động đều tự chứa mọi classes của JDK.”** Sai. Dynamic top phụ thuộc base.
11. **“Có thể nối mọi file `.jsa` thành một file dùng chung.”** Sai. VM quản lý archive format/layering.
12. **“Một dynamic archive trên JDK A chắc dùng được với base của JDK B.”** Sai.
13. **“`ArchiveClassesAtExit` cập nhật file cache liên tục khi app đang chạy.”** Sai.
14. **“Ứng dụng exit 0 chứng minh AppCDS đã được dùng.”** Sai. Phải kiểm tra CDS/class-load logs.
15. **“Thấy `java.lang.String` shared là đủ chứng minh custom app archive hoạt động.”** Sai.
16. **“`-Xshare:on` là chế độ tăng tốc hơn `auto`.”** Sai. `on` là strict và có nguy cơ làm fail startup.
17. **“JIT Code Cache lưu mặc định vào `.jsa` để các JVM khác tái dùng.”** Sai.
18. **“OS page cache ấm là dấu hiệu CDS enabled.”** Sai. Hai cơ chế độc lập.
19. **“Một framework cache có cùng rules như CDS archive.”** Sai. Mỗi provider định nghĩa contract riêng.
20. **“Cứ thêm CPU là archive sẽ tương thích.”** Sai. CPU có thể cải thiện tốc độ, không làm thay đổi binary compatibility.
21. **“CDS chia sẻ toàn bộ Java heap và static fields giữa processes.”** Sai. Chia class data, không chia mutable business state.
22. **“Cùng major JDK 17 là đủ khi build multi-arch image.”** Sai.
23. **“CDS compatibility failures phải luôn làm process crash.”** Sai. `auto` có thể fallback, `on` thường fail strict.
24. **“Không thấy nhiều GC events chứng minh archive đã dùng.”** Sai. GC logs không kiểm tra nguồn class metadata.
25. **“Tăng `-Xmx` luôn giải quyết archive mapping failure.”** Sai.
26. **“Archive được JDK chấp nhận nghĩa startup chắc giảm 50%.”** Sai. Phải đo workload thực.
27. **“Có thể dump archive khi app bị SIGKILL mà chắc được file đầy đủ.”** Sai.
28. **“File `.jsa` có tên hợp lệ thì nội dung chắc cũng hợp lệ.”** Sai. Cần integrity và VM validation.
29. **“CDS cache mang theo application config và secrets.”** Sai. Đó không phải heap/config snapshot.
30. **“Một JDK vendor mới chắc tương thích archive vendor cũ nếu cùng build number.”** Không được bảo đảm.
31. **“Cứ `java -jar` là runtime classpath luôn giống `-cp` lúc dump.”** Không phải một quy tắc tổng quát; launcher/class-loader behavior có thể khác.
32. **“Khi archive mismatch, nên tắt VM internal validation.”** Sai. Phải tái tạo archive đúng input.
33. **“AppCDS tự động cache tất cả future plugin classes.”** Sai. Eligibility/loading/trial profile có giới hạn.
34. **“Cần dùng `-Xshare:on` để xác minh in production.”** Sai. Test strict ở CI, tránh làm service dễ outage.
35. **“Một tag Docker bất biến theo tên nên archive cũng bất biến.”** Không chắc; tag có thể được republish, cần image digest.
36. **“CDS archive tương thích nghĩa input source code không đổi.”** Chưa đủ; VM build, JAR bytes/path, options, module config cũng quan trọng.

## 20. Tự kiểm tra và đáp án

**Câu 1.** Archive được tạo từ JDK 17.0.8 vendor A, chạy dưới JDK 17.0.9 vendor B. Có thể tin chắc file `.jsa` hợp lệ không?

**Đáp án:** Không. CDS archive là VM-build-specific artifact; tái tạo trên runtime JDK đích và xác minh.

**Câu 2.** Dump classpath là `a.jar:b.jar`; runtime classpath là `a.jar:b.jar:c.jar`. Có nhất thiết vi phạm classpath prefix rule không?

**Đáp án:** Không. Dump classpath là prefix của runtime classpath; nhưng các điều kiện khác vẫn phải thỏa, và classes cần được xác minh từ logs.

**Câu 3.** Dump classpath là `a.jar:b.jar`; runtime thành `b.jar:a.jar`. Cách xử lý?

**Đáp án:** Khôi phục order và JARs đúng hoặc tạo lại archive với classpath mục tiêu; không chỉ đổi archive filename.

**Câu 4.** Vì sao có `.jsa` và chương trình in kết quả đúng chưa đủ chứng minh AppCDS?

**Đáp án:** JVM có thể chạy không dùng archive, vẫn đúng Java semantics. Cần `-Xlog:cds` và `-Xlog:class+load` kiểm tra mapping/class source.

**Câu 5.** Dynamic archive có thể chuyển sang JDK khác chỉ cần giữ file top không?

**Đáp án:** Không bảo đảm. Top phụ thuộc base và VM assumptions tương ứng.

**Câu 6.** `-XX:ReservedCodeCacheSize` có làm file archive `.jsa` chứa machine code sau JIT warm-up không?

**Đáp án:** Không. Nó điều khiển in-process JIT code cache size, không tạo persistent AppCDS artifact.

**Câu 7.** `--patch-module` ảnh hưởng CDS thế nào theo Java 17 docs?

**Đáp án:** Vô hiệu CDS trong phạm vi hướng dẫn Oracle launcher.

**Câu 8.** Muốn dùng archive nhưng không muốn service bị fail chỉ vì CDS unusable, nên chọn `-Xshare:off` hay `-Xshare:auto`?

**Đáp án:** Thường chọn `-Xshare:auto` cùng logging/monitoring; `off` không dùng CDS, còn `on` strict có thể fail startup.

**Câu 9.** Default CDS archive của JDK và AppCDS custom archive có giống nhau không?

**Đáp án:** Không. Default chủ yếu chứa classes nền; custom AppCDS có thể thêm class ứng dụng và dependencies theo workflow.

**Câu 10.** Thấy class `ArchiveCompatibilityDemo` từ shared objects file thì đã đủ kết luận toàn bộ application classes đều shared chưa?

**Đáp án:** Chưa. Chỉ kết luận class cụ thể đó shared ở run này; kiểm tra những classes khác nếu cần.

**Câu 11.** Trong lab Java 17, stdout `totalChars` là bao nhiêu?

**Đáp án:** **12** từ độ dài `java`(4), `jvm`(3), `cache`(5).

**Câu 12.** Trong lab, `Runtime.version().feature()` in giá trị nào khi chạy trên JDK 17?

**Đáp án:** **17**.

**Câu 13.** Tại sao update app JAR cùng đường dẫn vẫn làm archive bị từ chối?

**Đáp án:** Binary contents/metadata và class identity assumptions không còn khớp với dữ liệu lúc dump.

**Câu 14.** Nếu app dùng nhiều custom class loaders/nested JARs, có được coi mọi lớp đều archivable không?

**Đáp án:** Không. Eligibility và startup behavior phụ thuộc loader/VM/framework, phải kiểm tra bằng runtime logs.

**Câu 15.** Đo memory tiết kiệm của nhiều JVMs bằng tổng RSS có thể sai thế nào?

**Đáp án:** Shared mapped pages bị tính trong RSS của nhiều processes; tổng RSS có thể đếm trùng. Cân nhắc PSS/USS hoặc OS tools phù hợp.

**Câu 16.** Vì sao OS page cache có thể làm kết quả startup benchmark sai lệch?

**Đáp án:** Những runs sau có thể đọc JAR/archive từ page cache đã ấm, nhanh hơn dù chính sách CDS không đổi. Cần nhiều runs và đảo thứ tự.

**Câu 17.** Nếu CI dùng JDK 17 nhưng production image chứa JDK 21, phải làm gì?

**Đáp án:** Không mang archive JDK 17 sang dùng như portable artifact. Dùng đúng production JDK/image khi generate archive và verify.

**Câu 18.** `-XX:ArchiveClassesAtExit` nên ghi ra đâu trong môi trường ephemeral pod?

**Đáp án:** Nên dùng job tạo archive có filesystem/artifact publishing phù hợp và graceful exit; file sinh trong layer ephemeral của pod có thể mất khi pod bị xóa.

## 21. Checklist dùng trước mỗi lần triển khai

- [ ] **JDK:** kiểm tra vendor/version/build, VM variant, OS/CPU architecture.
- [ ] **Đầu vào:** giữ immutable application/dependency JARs, lưu digests.
- [ ] **Classpath:** giữ đúng các JAR và thứ tự; kiểm tra same-or-prefix rule.
- [ ] **Module path:** dùng modular JARs phù hợp, tránh exploded modules trong CDS flow.
- [ ] **Module flags:** xác minh không dùng những options vô hiệu CDS theo Java 17 guide.
- [ ] **Custom loaders:** verify classes ứng dụng có thực sự được archive/share.
- [ ] **Base–top:** top dynamic phải gắn đúng base static/default và cùng runtime.
- [ ] **Archive file:** đúng path, quyền đọc, không hỏng, không bị ghi dở.
- [ ] **Build pipeline:** tạo và verify archive bằng runtime image/cấu hình production.
- [ ] **CI:** thực hiện smoke test với CDS log và application stdout.
- [ ] **Production:** ưu tiên availability và logging, không ép strict mode thiếu chiến lược fallback.
- [ ] **Observability:** lưu lý do CDS reject/skip và class load sources.
- [ ] **Benchmark:** so no-CDS/default/custom, cùng môi trường và metric.
- [ ] **Multi-arch:** sinh/check artifact phù hợp từng architecture.
- [ ] **Rebuild trigger:** thay JDK/JAR/modules/classpath ⇒ regenerate và test.
- [ ] **Cache khác:** áp dụng version/config/integrity contract riêng theo provider.

## 22. Tổng kết

```text
                       CÓ ARCHIVE / CACHE
                              │
                              ▼
                 XÁC ĐỊNH ĐÚNG LOẠI
                ┌─────────────┼──────────────┐
                │             │              │
             CDS/AppCDS     JIT Code       Framework cache
               .jsa          Cache          / snapshot
                │             │              │
                ▼             ▼              ▼
       JVM build + jars   Runtime-only    Provider-specific
       paths + VM flags   compiled code   compatibility key
       + base/top + OS         │              │
                │             │              │
                └─────────────┴──────────────┘
                              │
                              ▼
                VALIDATE IN TARGET RUNTIME
                              │
             ┌────────────────┴───────────────┐
             │                                │
         COMPATIBLE                       INCOMPATIBLE
             │                                │
             ▼                                ▼
     Share archived class data         Fallback / fail / rebuild
             │                                │
             └────────────────┬───────────────┘
                              ▼
                  SAME JAVA SEMANTICS
                              │
                              ▼
       VERIFY logs và đo startup/footprint thật
```

**Kết luận:** Archive hoặc cache khởi động nhanh **chỉ có giá trị khi đầu vào và runtime vẫn phù hợp với giả định lúc tạo**. Với **CDS/AppCDS Java 17**, kiểm tra **JDK/HotSpot build, OS/architecture, application JARs, classpath prefix/order, module constraints, base–dynamic archive và các JVM flags liên quan**. **`-Xshare:auto`** phù hợp hơn cho một service cần availability; **`-Xshare:on`** hữu ích để fail-fast trong kiểm thử nhưng có thể làm production không khởi động. Luôn kiểm tra `cds`/`class+load` logs để chứng minh archive thực sự được dùng; sau đó mới đo startup/footprint. **Đừng áp các quy tắc của CDS lên JIT Code Cache, framework caches hay cơ chế AOT của JDK khác**.

### Tài liệu tham khảo chính thức

- [Oracle JDK 17 — `java` launcher, Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): classpath/module rules, static/dynamic archive, base/top syntax, `Xshare` modes, `jcmd`.
- [Oracle Java SE 17 — Class Data Sharing](https://docs.oracle.com/en/java/javase/17/vm/class-data-sharing.html): default archive, dynamic archive, memory/startup goals, availability notes.
- [JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): cơ chế mở rộng CDS sang ứng dụng.
- [JEP 341 — Default CDS Archives](https://openjdk.org/jeps/341): default archive build cùng JDK.
- [JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): dynamic top archive và nguyên tắc sử dụng.
- [Oracle JDK 17 — `jcmd` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic commands trong môi trường có attach.
- [Oracle Java SE 17 — JVMS Chapter 4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): Java class-file format khác với binary CDS archive.
