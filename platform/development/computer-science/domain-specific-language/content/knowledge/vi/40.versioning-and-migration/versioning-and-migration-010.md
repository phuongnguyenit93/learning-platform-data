# Kiểm thử phiên bản

## 1. Kiểm thử phiên bản là gì?

Kiểm thử phiên bản (version testing) là quá trình xác minh một phiên bản DSL (Domain-Specific Language), compiler, runtime, plugin, schema hoặc artifact có hoạt động đúng theo hợp đồng đã công bố và tương thích với các thành phần mà nó cần phối hợp hay không.

Một hệ sinh thái DSL thường có nhiều version độc lập:

- Language version quy định cú pháp và ngữ nghĩa.
- Compiler version phân tích và tạo artifact.
- Runtime version thực thi artifact.
- Artifact format version mô tả cấu trúc package, bytecode hoặc IR.
- Runtime ABI version mô tả hợp đồng liên kết.
- Plugin API version mô tả khả năng mở rộng.
- Schema version mô tả cấu trúc dữ liệu.
- Language server và IDE extension version hỗ trợ developer tooling.

Một project có thể compile thành công bằng compiler mới nhưng artifact không chạy trên runtime cũ. Một source có thể vẫn parse được nhưng kết quả thay đổi do semantics của toán tử được cập nhật. Một migration có thể đổi schema thành công nhưng ứng dụng phiên bản trước không còn đọc được dữ liệu.

Kiểm thử phiên bản tìm ra các vấn đề này trước khi phát hành hoặc nâng cấp môi trường. Nó kiểm tra cả hành vi của một phiên bản riêng lẻ lẫn cách nhiều phiên bản tương tác.

## 2. Vì sao cần kiểm thử phiên bản?

DSL thường được sử dụng lâu dài trong nhiều project, workflow và ứng dụng. Khi compiler, runtime hoặc schema được nâng cấp, nhóm cần biết chương trình cũ có tiếp tục hoạt động đúng hay không.

Kiểm thử phiên bản giúp:

1. Phát hiện breaking change trước khi người dùng nâng cấp.
2. Xác nhận compiler và runtime tương thích.
3. Kiểm tra artifact cũ có thể được đọc hoặc thực thi hay không.
4. Bảo đảm semantics không đổi ngoài chủ đích.
5. Xác minh migration chuyển source, schema hoặc configuration chính xác.
6. Phát hiện dependency hoặc plugin không còn tương thích.
7. Duy trì khả năng tái lập build và deployment.
8. Kiểm tra deprecation warning và API replacement.
9. Cung cấp bằng chứng cho release và support matrix.
10. Giảm rủi ro khi triển khai phiên bản mới lên môi trường đang chạy.

Một version number tăng không tự chứng minh tính tương thích. Chính sách SemVer, release note và compatibility matrix cần được xác minh bằng test trên các tổ hợp version được hỗ trợ.

## 3. Phạm vi và các loại kiểm thử phiên bản

Kiểm thử phiên bản có thể được chia thành các nhóm:

| Nhóm | Mục tiêu |
|---|---|
| Language compatibility | Source cũ có còn hợp lệ và giữ semantics không? |
| Compiler regression | Compiler mới có tạo kết quả đúng không? |
| Runtime compatibility | Runtime có thực thi artifact từ compiler được hỗ trợ không? |
| Artifact compatibility | Package, bytecode, AST hoặc IR có đọc được qua version không? |
| API compatibility | Public API và plugin contract có bị phá vỡ không? |
| Schema compatibility | Dữ liệu và schema có tương thích giữa ứng dụng cũ/mới không? |
| Migration testing | Công cụ nâng cấp có chuyển đổi chính xác không? |
| Tooling compatibility | IDE, language server, formatter và debugger có phối hợp đúng không? |
| Dependency compatibility | Dependency trực tiếp và bắc cầu có đáp ứng constraints không? |
| Deployment compatibility | Artifact, runtime, configuration và hạ tầng có thể triển khai cùng nhau không? |

Một release có thể cần nhiều nhóm test. Ví dụ nâng compiler nhưng giữ runtime không đổi vẫn cần language compatibility, artifact compatibility và regression test; nâng schema có thể cần migration test và kiểm tra backward compatibility.

## 4. Phân biệt version và compatibility

Version là định danh một bản phát hành. Compatibility là khả năng hai thành phần hoặc hai phiên bản phối hợp theo một hợp đồng.

Ví dụ:

~~~text
Compiler 4.2 -> Artifact format 3
Runtime 5.0 -> Supports artifact format 2 and 3
Runtime 4.8 -> Supports artifact format 2 only
~~~

Compiler 4.2 có thể tương thích với Runtime 5.0 nhưng không tương thích với Runtime 4.8. Không thể suy ra điều này chỉ từ số version.

### 4.1. Backward compatibility

Phiên bản mới tiếp tục hỗ trợ source, API hoặc artifact được tạo theo phiên bản cũ trong phạm vi đã công bố.

Ví dụ, compiler mới vẫn parse cú pháp DSL version 2 và giữ semantics cũ khi source khai báo version 2.

### 4.2. Forward compatibility

Thành phần cũ có thể xử lý dữ liệu hoặc artifact từ phiên bản mới ở mức được quy định. Điều này thường khó hơn backward compatibility vì thành phần cũ có thể không hiểu feature mới.

Ví dụ, một reader có thể bỏ qua metadata field không bắt buộc mà nó chưa biết, nhưng không thể tự động hiểu instruction bytecode mới.

### 4.3. Source compatibility

Source compatibility nghĩa là chương trình cũ tiếp tục compile hoặc được chuyển đổi với ít thay đổi. Nó không tự bảo đảm runtime behavior giống nhau.

### 4.4. Binary và ABI compatibility

Binary compatibility liên quan tới khả năng liên kết hoặc tải artifact đã biên dịch. ABI compatibility bao gồm calling convention, layout dữ liệu, symbol và runtime contract.

### 4.5. Behavioral compatibility

Behavioral compatibility yêu cầu hành vi quan sát được giữ nguyên theo contract, kể cả khi internal implementation thay đổi.

## 5. Semantic Versioning và kiểm thử

SemVer thường dùng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi không tương thích.
- MINOR: thêm tính năng tương thích ngược.
- PATCH: sửa lỗi tương thích.

Kiểm thử cần xác minh release đúng với cam kết:

| Loại release | Kỳ vọng kiểm thử |
|---|---|
| Patch | Regression fix, không tạo breaking change ngoài chủ đích |
| Minor | Tính năng mới hoạt động, source/API cũ tiếp tục hoạt động |
| Major | Breaking changes được xác định, migration và upgrade path được kiểm tra |
| Pre-release | Feature thử nghiệm, compatibility risk và migration được ghi rõ |

Một bug fix có thể thay đổi output của chương trình trước đó phụ thuộc vào behavior sai. Khi đó release note cần nêu hành vi thay đổi và test cần phân biệt bug fix với contract change.

### 5.1. Language version khác compiler version

Compiler 5.x có thể hỗ trợ nhiều language version. Source cần khai báo language version để compiler không âm thầm đổi semantics khi được nâng cấp.

Ví dụ:

~~~text
languageVersion = 3
~~~

Kiểm thử cần chạy cùng source trên compiler versions khác nhau với language version được cố định để xác nhận contract.

## 6. Compatibility matrix

Compatibility matrix liệt kê các tổ hợp version được hỗ trợ và đã kiểm thử.

Ví dụ minh họa:

| Compiler | Language version | Artifact format | Runtime được hỗ trợ |
|---|---|---|---|
| 3.8 | 2 | 2 | Runtime 4.x |
| 4.2 | 2, 3 | 2, 3 | Runtime 4.x, 5.x |
| 5.0 | 3, 4 | 3, 4 | Runtime 5.x, 6.x |

Bảng thực tế cần chỉ rõ minor/patch range, platform, ABI và feature capability khi chúng ảnh hưởng compatibility.

### 6.1. Chọn tổ hợp cần kiểm thử

Không phải lúc nào cũng cần kiểm thử mọi tổ hợp giữa tất cả compiler, runtime, plugin và platform. Có thể:

- Kiểm thử đầy đủ các tổ hợp được hỗ trợ.
- Kiểm thử boundary versions.
- Kiểm thử version mới nhất và version cũ nhất trong support window.
- Kiểm thử tổ hợp được sử dụng phổ biến.
- Kiểm thử tổ hợp có rủi ro cao hoặc có thay đổi liên quan.

Mỗi tổ hợp không được kiểm thử cần được đánh dấu unsupported hoặc unverified, không nên ngầm hiểu là tương thích.

### 6.2. Compatibility gate

Build hoặc deployment pipeline có thể kiểm tra manifest so với matrix:

~~~text
project compiler: 4.2.1
project runtime: 5.0.2
artifact format: 3

matrix result: supported
~~~

Nếu tổ hợp không được hỗ trợ, pipeline nên dừng với thông báo nêu rõ version yêu cầu và các tổ hợp hợp lệ.

## 7. Kiểm thử source compatibility

Source compatibility test dùng một corpus chương trình DSL đã tồn tại qua nhiều phiên bản.

Corpus nên gồm:

- Chương trình cơ bản.
- Type và function phổ biến.
- Generic và overload.
- Macro hoặc extension nếu có.
- Query và workflow đại diện.
- Cú pháp deprecated.
- Trường hợp biên và lỗi được kỳ vọng.

Một quy trình:

1. Chọn source được tạo bởi phiên bản cũ.
2. Compile bằng compiler mới.
3. Ghi nhận warning và error.
4. So sánh output hoặc semantics với baseline.
5. Xác định thay đổi nào được chủ đích.

### 7.1. Compile-only compatibility

Compile-only test xác nhận source vẫn được chấp nhận. Nó không xác nhận behavior khi chạy. Cần runtime test cho những chương trình có semantics quan trọng.

### 7.2. Warning compatibility

Phiên bản mới có thể thêm warning cho cú pháp deprecated. Test nên xác nhận warning xuất hiện đúng vị trí và không biến thành error ngoài policy.

### 7.3. Source formatting

Formatter mới có thể thay đổi cách trình bày source. Nếu project dùng generated formatting hoặc format check, cần kiểm tra diff và bảo đảm formatter không đổi semantics.

## 8. Kiểm thử semantic regression

Semantic regression test xác nhận cùng chương trình và input vẫn tạo hành vi theo contract sau khi nâng compiler hoặc runtime.

Ví dụ:

~~~text
let result = 10 / 4
assert result == expectedValue
~~~

Test cần cố định type và numeric semantics để không so sánh kết quả mơ hồ.

Các nhóm semantics cần test:

- Scope và name resolution.
- Type inference và overload.
- Evaluation order.
- Short-circuit.
- Null và missing value.
- Numeric overflow và rounding.
- String và Unicode.
- Date/time và timezone.
- Exception propagation.
- Side effect và transaction.
- Concurrency và cancellation.
- Query ordering và aggregation.
- Workflow state transition.

### 8.1. Golden test

Golden test lưu output mong đợi từ một bộ input. Khi compiler mới tạo output khác, diff cho thấy thay đổi.

Golden test hữu ích cho:

- Generated source.
- Bytecode hoặc normalized IR.
- Diagnostics.
- Documentation.
- Serialized artifact.

Không nên cập nhật golden file tự động mà không xem xét diff. Output mới có thể phản ánh breaking change hoặc bug.

### 8.2. Differential testing

Chạy cùng source trên compiler/runtime cũ và mới rồi so sánh kết quả. Cần phân biệt:

- Khác biệt được chủ đích.
- Khác biệt do bug đã sửa.
- Regression không mong muốn.
- Output không deterministic.

Nếu backend có nondeterminism được cho phép, cần so sánh invariant hoặc normalized result thay vì byte output tuyệt đối.

### 8.3. Property-based testing

Sinh nhiều input theo property để kiểm tra semantics tổng quát. Ví dụ, serialize rồi deserialize một giá trị hợp lệ phải giữ giá trị; format rồi parse lại phải giữ AST hoặc semantics theo contract.

## 9. Kiểm thử compiler version

Compiler mới cần được kiểm tra theo các giai đoạn:

- Lexer và parser.
- Name resolution.
- Type checking.
- Semantic analysis.
- Optimization.
- Code generation.
- Artifact packaging.
- Diagnostic và source mapping.

Một thay đổi ở parser có thể làm source cũ không parse; một thay đổi optimizer có thể tạo kết quả sai; một thay đổi code generator có thể làm artifact không chạy trên runtime được hỗ trợ.

### 9.1. Compiler regression corpus

Giữ corpus gồm source hợp lệ, source lỗi và các trường hợp biên. Mỗi bug đã sửa có thể bổ sung một fixture để ngăn lỗi tái xuất hiện.

### 9.2. Compiler output comparison

Có thể so sánh AST, IR, bytecode hoặc generated source. Cần chuẩn hóa những metadata không có ý nghĩa như temporary ID hoặc timestamp nếu mục tiêu là so sánh semantics.

### 9.3. Diagnostic compatibility

Diagnostic có thể thay đổi câu chữ giữa các version. Nếu tool hoặc test phụ thuộc diagnostic code, nên giữ code ổn định và chỉ thay message khi cần.

## 10. Kiểm thử runtime và ABI compatibility

Runtime cần kiểm tra artifact được tạo từ compiler trong compatibility matrix.

Các kiểm thử:

- Runtime load artifact.
- Resolve symbol và function.
- Calling convention và data layout.
- Standard library behavior.
- Exception và error mapping.
- Memory/resource behavior.
- Runtime API deprecation.
- Artifact metadata validation.

Ví dụ ma trận:

~~~text
compiler 4.2 -> runtime 5.0: supported
compiler 4.2 -> runtime 4.8: unsupported
compiler 3.8 -> runtime 5.0: supported via format 2
~~~

### 10.1. Artifact format

Artifact format cần version riêng nếu cấu trúc có thể thay đổi độc lập với compiler version. Test cần:

- Reader mới đọc artifact cũ.
- Reader cũ từ chối artifact mới với lỗi rõ ràng.
- Unknown optional field được xử lý theo contract.
- Corrupt artifact bị phát hiện.
- Signature hoặc checksum được xác minh trước load nếu cần.

### 10.2. ABI

Nếu runtime ABI thay đổi, cần kiểm tra function call, object layout, exception, memory ownership và native extension. Một artifact có thể parse được nhưng vẫn crash hoặc sai dữ liệu khi ABI không tương thích.

## 11. API và plugin compatibility

Framework hoặc workbench có thể cung cấp public API cho plugin:

- Compiler extension API.
- Parser/AST API.
- Runtime function registry.
- Language server protocol.
- Debug adapter API.
- Build plugin API.

Kiểm thử API compatibility nên xác nhận:

- Public method hoặc symbol không bị xóa ngoài chính sách.
- Signature và generic constraints giữ contract.
- Visibility và default behavior không đổi bất ngờ.
- Plugin cũ có thể load trong support range.
- API deprecated phát warning và replacement đúng.
- Binary compatibility nếu hệ sinh thái yêu cầu.

### 11.1. Plugin fixture

Giữ một số plugin mẫu được build bằng các API version cũ. Khi nâng framework, thử load hoặc compile chúng theo compatibility matrix.

### 11.2. Capability negotiation

Plugin hoặc LSP client có thể hỗ trợ một tập capability khác nhau. Test cần xác nhận fallback khi capability không có và không gửi protocol feature mà client chưa công bố hỗ trợ.

### 11.3. Extension API

Nếu framework có internal API không được bảo đảm tương thích, cần đánh dấu rõ. Không nên dùng test của public API để ngầm cam kết compatibility cho internal API.

## 12. Schema compatibility

DSL thường tham chiếu schema của database, event, API hoặc domain object. Schema evolution có thể làm source compile lỗi hoặc runtime behavior thay đổi.

Các thay đổi schema:

- Thêm field optional.
- Thêm field required.
- Xóa field.
- Đổi tên field.
- Đổi type.
- Thay enum value.
- Đổi default.
- Thay constraint.
- Thay quan hệ hoặc cardinality.

### 12.1. Backward-compatible schema change

Thêm field optional thường ít gây phá vỡ hơn xóa field hoặc đổi kiểu, nhưng vẫn có thể ảnh hưởng code generator, serializer hoặc query wildcard.

### 12.2. Forward-compatible reader

Reader cũ có thể bỏ qua field mới nếu format cho phép. Nhưng nếu field mới làm thay đổi semantics hoặc invariant, bỏ qua có thể không an toàn.

### 12.3. Schema contract test

Kiểm tra producer và consumer ở các version khác nhau:

~~~text
producer v2 -> consumer v1
producer v1 -> consumer v2
producer v2 -> consumer v2
~~~

Không phải mọi hướng đều phải được hỗ trợ. Matrix cần ghi rõ compatibility được cam kết.

## 13. Kiểm thử migration

Migration test xác nhận công cụ chuyển đổi source, schema, artifact hoặc configuration từ version cũ sang version mới.

Migration có thể gồm:

- Cập nhật syntax DSL.
- Đổi API hoặc function name.
- Chuyển schema.
- Chuyển workflow definition.
- Nâng artifact format.
- Cập nhật build manifest.
- Thay đổi configuration key.

Ví dụ:

~~~text
old:
  requireReview(orderId)

new:
  requireManualReview(orderId)
~~~

Một migration tool nên dùng parser/AST khi thay đổi cấu trúc source, thay vì thay chuỗi toàn cục có thể sửa nhầm comment hoặc string.

### 13.1. Migration fixture

Chuẩn bị project fixture ở mỗi source version được hỗ trợ. Chạy migration và xác nhận:

- Output parse được.
- Type checking thành công.
- Semantics giữ đúng hoặc thay đổi theo migration spec.
- Comment và formatting quan trọng được giữ.
- Import và dependency được cập nhật.
- Diagnostic nêu trường hợp không thể tự động chuyển.

### 13.2. Idempotence

Nếu migration được thiết kế idempotent, chạy hai lần phải cho cùng kết quả như chạy một lần. Test này phát hiện tool vô tình lặp thay đổi hoặc tạo source hỏng khi chạy lại.

### 13.3. Migration có mất mát

Một chuyển đổi có thể không tự động bảo toàn toàn bộ thông tin. Tool cần báo rõ những trường hợp cần quyết định của người dùng, thay vì âm thầm xóa hoặc suy diễn dữ liệu.

### 13.4. Rollback

Nếu migration thay đổi data hoặc artifact, cần kiểm tra có thể phục hồi từ backup hoặc migration ngược hay không. Không phải migration nào cũng có inverse transformation.

## 14. Deprecation testing

Deprecation là giai đoạn thông báo một API hoặc syntax không còn được khuyến nghị và có thể bị loại bỏ.

Test cần xác nhận:

- API cũ vẫn hoạt động trong version hỗ trợ.
- Warning xuất hiện đúng vị trí.
- Replacement được chỉ ra chính xác.
- API mới có semantics tương ứng.
- Removal chỉ xảy ra ở version đã công bố.
- Migration tool xử lý trường hợp phổ biến.

Ví dụ:

~~~text
@deprecated(since = "4.2", replacement = "requireManualReview")
function requireReview(orderId: OrderId)
~~~

Warning nên có diagnostic code ổn định để IDE và CI có thể lọc hoặc hiển thị. Không nên biến mọi deprecation thành error trước khi support policy quy định.

## 15. Kiểm thử dependency và toolchain

Toolchain DSL có thể phụ thuộc:

- Parser generator.
- Runtime library.
- Build plugin.
- Formatter.
- Documentation generator.
- IDE extension.
- Native compiler.
- Package manager.

Khi nâng dependency, cần kiểm tra:

- Version range và lockfile.
- Dependency bắc cầu.
- Checksum hoặc signature.
- License và security advisory.
- API compatibility.
- Platform support.
- Reproducible build.

### 15.1. Dependency matrix

Nếu compiler hỗ trợ nhiều JDK hoặc OS, có thể cần matrix theo platform:

| Compiler | JDK | OS | Kết quả |
|---|---|---|---|
| 4.2 | 17 | Linux | Supported |
| 4.2 | 21 | Linux | Supported |
| 4.2 | 21 | Windows | Supported |
| 4.2 | 11 | Linux | Unsupported |

Đây là ví dụ minh họa. Chỉ ghi Supported khi tổ hợp đã được kiểm thử hoặc có cam kết chính thức.

### 15.2. Lockfile verification

Build cần xác nhận lockfile được dùng và checksum đúng. Nếu resolver tự chọn dependency mới ngoài lockfile, kết quả test không còn chứng minh được compatibility của tổ hợp đã khai báo.

## 16. Kiểm thử IDE, language server và formatter

Developer tooling có thể có version cycle riêng với compiler.

Các kiểm thử:

- IDE nhận diện language version.
- Syntax highlighting đúng với grammar.
- Completion dựa trên schema và symbol mới.
- Hover hiển thị đúng documentation.
- Diagnostic khớp compiler.
- Rename và go-to-definition hoạt động.
- Formatter không làm đổi semantics.
- Debugger hiểu source map của artifact.
- LSP capability negotiation đúng với client cũ.

### 16.1. Editor compatibility

Một extension có thể yêu cầu editor version tối thiểu. Test cần xác nhận activation, command registration, document sync và protocol feature.

### 16.2. Formatter compatibility

Formatter mới có thể đổi layout nhưng không nên đổi semantics. Có thể parse source trước và sau formatting rồi so sánh AST hoặc chạy conformance tests.

### 16.3. Language server/compiler parity

Nếu language server dùng compiler library riêng, version drift có thể làm IDE chấp nhận source mà build từ chối hoặc ngược lại. Cần test parity trên cùng corpus.

## 17. Kiểm thử generated artifact và documentation

Compiler hoặc generator có thể tạo:

- Source code.
- Bytecode.
- Schema.
- API reference.
- Documentation site.
- Workflow bundle.

Version test nên xác nhận:

- Output có đúng format version.
- Generated source compile được với target toolchain.
- Cross-reference và source mapping hợp lệ.
- Documentation phản ánh semantics của language version.
- Artifact có thể được load bởi runtime được hỗ trợ.
- Output deterministic theo mức cam kết.

Golden-file test hữu ích nhưng cần normalize timestamp, path hoặc metadata không có ý nghĩa nếu mục tiêu là so sánh nội dung.

## 18. Compatibility của query và workflow

DSL query và workflow có semantics riêng cần kiểm thử khi version thay đổi.

### 18.1. Query compatibility

Kiểm tra:

- Null và missing behavior.
- Ordering và pagination.
- Aggregate semantics.
- Join cardinality.
- Numeric conversion.
- Timezone.
- Backend pushdown.
- Authorization policy.
- Query plan correctness.

Cùng query chạy trên compiler/engine mới cần giữ kết quả theo contract hoặc ghi rõ thay đổi.

### 18.2. Workflow compatibility

Kiểm tra:

- Workflow definition cũ có load được không.
- Instance đang chạy được tiếp tục bằng version nào.
- Event schema có tương thích không.
- Retry và timeout semantics có đổi không.
- Activity API có còn tồn tại không.
- Compensation và replay có giữ semantics không.

Workflow đang chạy lâu dài có thể được pin vào definition version cũ. Không nên tự động áp dụng semantics mới cho instance cũ nếu chưa có migration hoặc versioning policy.

## 19. Kiểm thử deployment và runtime upgrade

Deployment test xác nhận artifact, runtime, configuration và schema có thể phối hợp.

Các kịch bản:

- Nâng runtime nhưng giữ artifact cũ.
- Nâng artifact nhưng giữ runtime trong support range.
- Rolling upgrade với instance cũ và mới cùng tồn tại.
- Blue/green deployment.
- Rollback application sau schema migration.
- Restart worker khi workflow đang chờ.
- Restore backup và tiếp tục execution.

### 19.1. Expand-and-contract migration

Một cách nâng schema an toàn:

1. Expand: thêm field hoặc cấu trúc mới nhưng vẫn giữ cấu trúc cũ.
2. Deploy code có thể đọc cả hai dạng.
3. Migrate dữ liệu.
4. Chuyển writer sang dạng mới.
5. Verify không còn consumer dùng cấu trúc cũ.
6. Contract: xóa cấu trúc cũ trong release sau.

Test cần bao gồm trạng thái trung gian, không chỉ schema trước và sau cuối cùng.

### 19.2. Rolling upgrade

Trong rolling upgrade, nhiều runtime version có thể chạy cùng lúc. Cần kiểm tra event, message và artifact được tạo bởi version mới có thể được worker cũ đọc hay không.

## 20. Test strategy theo tầng

Một chiến lược test phiên bản có thể chia thành:

| Tầng | Nội dung | Mục đích |
|---|---|---|
| Unit | Type rule, parser rule, migration function | Phát hiện lỗi cục bộ |
| Conformance | Semantic rules và expected behavior | Xác nhận hợp đồng DSL |
| Compatibility | Compiler/runtime/API matrix | Xác nhận tổ hợp version |
| Integration | Database, connector, plugin và build tool | Kiểm tra phối hợp |
| End-to-end | Build, deploy, execute workflow/query | Xác nhận luồng thật |
| Upgrade/migration | Nâng source, schema và artifact | Kiểm tra đường nâng cấp |
| Performance regression | Latency, throughput, memory và build time | Phát hiện suy giảm |
| Security regression | Dependency, policy và artifact integrity | Ngăn lỗi bảo mật tái xuất |

Test ở tầng thấp chạy thường xuyên; test matrix lớn có thể chạy theo lịch hoặc trước release candidate. Release gate cần chọn đủ test để bảo vệ rủi ro chính.

## 21. Test data và versioned fixtures

Fixture cần ghi rõ version:

~~~text
fixtures/
  language-v2/
  language-v3/
  artifact-format-v2/
  artifact-format-v3/
  schema-v4/
  schema-v5/
~~~

Mỗi fixture nên có metadata:

- Version tạo fixture.
- Compiler hoặc runtime nguồn.
- Expected result.
- Migration path nếu có.
- Test case liên quan.

Không nên regenerate toàn bộ fixture bằng compiler mới mà không giữ bản cũ, vì có thể làm mất baseline cần thiết để phát hiện regression.

## 22. Test matrix và tự động hóa CI

Một CI matrix có thể kiểm tra compiler/runtime:

~~~yaml
strategy:
  matrix:
    compiler: ["3.8", "4.2", "5.0"]
    runtime: ["4.8", "5.0", "6.0"]
~~~

Trong thực tế, cần lọc matrix theo compatibility support. Không phải mọi tổ hợp đều cần chạy hoặc đều được phép.

### 22.1. Fast checks và full matrix

- Pull request: unit, conformance subset, compile corpus và API check.
- Nightly: full compatibility matrix, integration và performance regression.
- Release candidate: migration, deployment, security và end-to-end.

### 22.2. Fail-fast

Nếu manifest yêu cầu compiler 4.2 nhưng CI đang chạy 5.0, pipeline nên báo mismatch ngay. Không nên để test chạy với toolchain không đúng rồi tạo kết quả khó diễn giải.

### 22.3. Test result provenance

Kết quả test nên gắn compiler/runtime version, lockfile hash, platform và fixture revision. Nếu không, một pass result có thể không áp dụng cho artifact hoặc tổ hợp version đang phát hành.

## 23. Performance compatibility

Phiên bản mới có thể giữ correctness nhưng làm hiệu năng suy giảm.

Các chỉ số cần so sánh:

- Parse/compile time.
- Startup time.
- Runtime latency p50/p95/p99.
- Throughput.
- CPU và memory.
- GC pause.
- Query rows/bytes scanned.
- Workflow queue wait.
- Artifact size.

### 23.1. Baseline

Giữ benchmark có version và workload rõ. Không so sánh số liệu từ hai môi trường khác nhau rồi kết luận compiler mới chậm hơn.

### 23.2. Threshold

Có thể đặt regression threshold, ví dụ p95 latency không được tăng quá một mức đã thống nhất trong workload quan trọng. Threshold cần xét variance và noise của benchmark.

### 23.3. Không đánh đổi correctness

Nếu tối ưu mới tăng tốc nhưng thay đổi semantics, đó là compatibility regression trừ khi behavior change đã được công bố và version hóa.

## 24. Security compatibility

Nâng version có thể thay đổi authentication, authorization, serialization hoặc sandbox behavior.

Kiểm thử:

- Policy cũ có giữ quyền đúng không.
- Default permission có thay đổi không.
- Artifact signature được xác minh thế nào.
- Token và credential có được parse đúng.
- Deserialization có chấp nhận format không an toàn không.
- Sandbox và resource limits có còn hoạt động.
- Dependency mới có vulnerability đã biết không.

Một release không nên được xem là compatible chỉ vì test chức năng pass nếu nó làm mở rộng quyền truy cập ngoài chủ đích.

## 25. Kiểm thử rollback và phục hồi

Rollback test xác nhận có thể quay lại phiên bản ổn định trước đó trong điều kiện được hỗ trợ.

Các câu hỏi:

- Artifact cũ còn được lưu và xác minh không?
- Runtime cũ có đọc được schema hiện tại không?
- Configuration mới có tương thích với ứng dụng cũ không?
- Workflow đang chạy có tiếp tục được không?
- Migration có thể đảo ngược không?
- External side effect đã xảy ra có cần compensation không?

Rollback application không đồng nghĩa rollback data. Test cần mô phỏng cả hai phần.

## 26. Quản lý kết quả và triage

Khi version test thất bại, cần phân loại:

- Test infrastructure failure.
- Unsupported version combination.
- Expected breaking change.
- Unexpected source incompatibility.
- Semantic regression.
- Artifact/ABI incompatibility.
- Migration defect.
- Performance regression.
- Security regression.

Mỗi failure cần lưu:

- Version và platform.
- Source fixture hoặc artifact digest.
- Test case ID.
- Expected và actual result.
- Log/trace có liên quan.
- Mức ảnh hưởng.
- Owner và quyết định xử lý.

Không nên bỏ qua test fail chỉ vì nó xuất hiện ở tổ hợp ít dùng. Nếu tổ hợp đó được công bố hỗ trợ, failure vẫn cần được giải quyết hoặc support matrix phải được điều chỉnh minh bạch.

## 27. Những lỗi thường gặp khi kiểm thử phiên bản

### Chỉ test phiên bản mới nhất

Người dùng đang chạy version cũ không được bảo vệ. Giữ fixture và matrix cho support window.

### Chỉ kiểm tra compile

Source có thể compile nhưng behavior thay đổi. Bổ sung semantic regression và runtime tests.

### Không test artifact cũ

Runtime mới có thể không đọc được bundle đã phát hành. Giữ artifact fixture từ các version được hỗ trợ.

### Chỉ test migration trên project nhỏ

Migration có thể lỗi với import phức tạp, comment hoặc cấu trúc lớn. Dùng corpus thực tế đã ẩn dữ liệu nhạy cảm.

### Regenerate golden file vô điều kiện

Baseline bị ghi đè và regression biến mất. Review diff và giữ expected result có version.

### Không kiểm thử trạng thái trung gian

Rolling upgrade hoặc expand-and-contract có thể lỗi dù trạng thái cuối cùng hợp lệ. Test từng giai đoạn.

### Matrix quá rộng nhưng không có mục tiêu

CI tốn thời gian mà không tăng độ tin cậy tương xứng. Chọn tổ hợp theo support policy và risk.

### Không ghi version vào test result

Không thể biết pass result áp dụng cho compiler hoặc runtime nào. Lưu provenance của test.

### Bỏ qua hiệu năng và bảo mật

Correctness pass nhưng latency hoặc quyền truy cập bị suy giảm. Có performance và security regression suite.

## 28. Quy trình kiểm thử một lần nâng phiên bản

Một quy trình có thể thực hiện:

1. **Đọc release notes và support matrix.** Xác định breaking changes, deprecation và version range.
2. **Khóa toolchain test.** Ghi compiler, runtime, plugin, dependency và platform.
3. **Chọn corpus.** Bao gồm source, artifact, schema, query và workflow đại diện.
4. **Chạy baseline cũ.** Lưu expected result và metric.
5. **Chạy compiler/runtime mới.** Thu thập compile, runtime và diagnostic result.
6. **Kiểm tra compatibility matrix.** Chỉ chạy tổ hợp được hỗ trợ hoặc cần xác nhận.
7. **Chạy migration test.** Nâng source, schema, artifact và configuration.
8. **Kiểm tra plugin/tooling.** IDE, language server, formatter và build integration.
9. **Chạy performance/security regression.** So sánh latency, resource và policy.
10. **Kiểm tra deployment/rollback.** Thử trạng thái trung gian và phục hồi.
11. **Phân loại sai khác.** Expected change, regression hay unsupported combination.
12. **Cập nhật tài liệu và support matrix.** Công bố kết quả và giới hạn.

## 29. Ví dụ end-to-end: nâng compiler DSL

Một project hiện dùng compiler 4.2, runtime 5.0, language version 3 và artifact format 3. Nhóm muốn nâng compiler lên 5.0.

### 29.1. Chuẩn bị

- Đọc release notes compiler 5.0.
- Xác định language version 3 còn được hỗ trợ.
- Xác nhận runtime 5.0 có đọc artifact format mới hay không.
- Chuẩn bị source corpus và artifact từ release hiện tại.

### 29.2. Test

1. Compile source corpus bằng compiler 4.2 để tạo baseline.
2. Compile cùng source bằng compiler 5.0 với language version 3.
3. So sánh diagnostics, normalized IR và generated artifact.
4. Chạy artifact mới trên runtime 5.0.
5. Chạy artifact cũ trên runtime mới nếu matrix cam kết.
6. Chạy conformance suite về null, numeric, scope và evaluation order.
7. Chạy query/workflow integration tests.
8. Chạy migration cho API đã deprecated.
9. Đo compile time và runtime latency.
10. Thử deploy staging và rollback về artifact cũ.

### 29.3. Kết quả minh họa

| Kiểm tra | Kết quả |
|---|---|
| Source compile với language version 3 | Pass |
| Runtime load artifact format 3 | Pass |
| Semantic conformance | Pass |
| Plugin API compatibility | Pass |
| Migration fixture | 1 case cần chỉnh thủ công |
| Compile time | Tăng 4% |
| Runtime p95 | Không thay đổi đáng kể |
| Rollback | Pass với schema hiện tại |

Các số liệu là ví dụ để minh họa báo cáo. Trong một lần nâng cấp thực tế, cần đính kèm test run, environment và artifact identity.

### 29.4. Quyết định release

Nếu một migration case cần can thiệp thủ công, release note và migration guide phải chỉ rõ trường hợp đó. Không nên tuyên bố migration tự động hoàn toàn khi fixture cho thấy có source không thể chuyển an toàn.

## 30. Kết luận

Kiểm thử phiên bản xác minh rằng compiler, runtime, language, artifact, schema, plugin và công cụ DSL phối hợp đúng theo support policy. Nó bao gồm source compatibility, semantic regression, ABI và artifact compatibility, API/plugin compatibility, migration, deployment, performance và security.

Một chiến lược hiệu quả kết hợp compatibility matrix, corpus source/artifact có version, conformance tests, golden/differential tests và migration fixtures. CI cần ghi rõ toolchain và môi trường của mỗi kết quả, còn release process cần kiểm tra cả trạng thái trung gian và rollback.

Khi kiểm thử phiên bản được thực hiện cùng quá trình phát triển và phát hành, nhóm có thể phát hiện breaking change sớm, cung cấp migration path rõ ràng và nâng cấp DSL mà vẫn bảo vệ các chương trình cùng dữ liệu đã được triển khai trước đó.
