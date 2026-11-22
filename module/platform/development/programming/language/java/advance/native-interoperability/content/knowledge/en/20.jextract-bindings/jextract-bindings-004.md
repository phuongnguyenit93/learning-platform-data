# Configuring Header Paths, Macros, and Declarations to Export When Generating jextract Bindings

`jextract` is a tool from the OpenJDK Code Tools project that **parses C headers (.h)** and generates Java bindings using the **Foreign Function & Memory API (FFM)**. When a Java project needs to call a C library, configuring `jextract` properly is not just pointing to a `.h` file: you must provide **search paths for headers included by the main file**, **preprocessor macros compatible with the actual C binary**, and **the list of declarations desired in the Java API**. Those three groups determine both which symbols are visible and which Java classes/methods are generated.

**Core idea:** `-I` helps Clang find headers; `-D` determines `#if`/`#ifdef` branches and type configuration; `--include-function`/`--include-struct`/`--include-constant` and corresponding filters determine which declarations get bindings. **Headers describe the ABI, while the actual native binary provides the functions and data.** If the headers and the binary were compiled with different macros, the generated code may be missing methods, have methods whose symbols cannot be found, or worse, pass the wrong layout/calling convention leading to a crash.

> **Version:** FFM `java.lang.foreign` was standardized in **JDK 22 (JEP 454)**. The complete examples below are for **Linux x86-64, JDK 22+, and a `jextract` build compatible with the JDK in use**. `jextract` is a separately distributed tool, not a command always available in the `bin` directory of every JDK. APIs and options across `jextract` versions may change: verify with `jextract --version`/`jextract --help` of your actual binary and pin the toolchain in your project. Java 17 had an FFM incubator with a different API, so Java 22+ samples will not compile as-is on it.

## 1. Diagram from header to Java bindings

```text
C library project
  include/
    demo/
      build.h             <- defines default macros
      api.h               <- public API, #include <demo/build.h>
  src/
    demoapi.c             <- actual implementation
          |
          +-- C compiler -I include -D... --> libdemoapi.so
          |
          +-- jextract   -I include -D... --> generated/*.java
                                        |
                                        +-- Java package
                                        +-- header/symbol class
                                        +-- struct/union/typedef wrappers
                                        +-- static methods down to native functions
                                        |
                                  javac + FFM runtime
                                        |
                                      Java app
                                           |
                                  native symbol lookup
                                           |
                                      libdemoapi.so
```

The two middle paths must **match each other**:

- **The C compiler** reads the headers and sources with its own `-I`, `-D`, and produces a shared library containing native symbols.
- **jextract** uses Clang to parse the headers (after C preprocessing) with its own `-I`, `-D`, and generates Java bindings according to the declarations it sees.
- **The Java runtime** loads/looks up the native library via `--library`/library lookup and calls functions through FFM.

`jextract` **does not compile the C implementation into a shared library**. It does not replace `cc`/`clang`/`gcc` and does not guarantee that a symbol name in the header actually exists in `.so`/`.dll`. A C prototype present in a header is only a declaration; the generated Java code still needs a matching native binary at runtime.

## 2. Three important configuration groups

| Group | `jextract` option | Effect | What it is NOT |
| --- | --- | --- | --- |
| Root header | `path/to/api.h` argument at the end of the command | Translation unit / starting file to parse | Not a shared library |
| Header search path | `-I dir` or `--include-dir dir` | Tells the C preprocessor where to find `#include` | Not a Java classpath or runtime library path |
| Preprocessor macro | `-D NAME=VALUE` or `--define-macro NAME=VALUE` | Changes declarations/type generation controlled by `#if` | Not a Java system property or automatic constant generator |
| Java output | `--output generated` | Root directory containing generated Java files | Not the native loader's classpath |
| Package | `--target-package demo.binding` or `-t` | Namespace of generated Java classes | Does not change C symbol names |
| Header class | `--header-class-name DemoNative` | Name of the root Java class holding functions/constants | Does not change the C header filename or library ABI |
| Native library | `--library name` or `-l name` | Library from which generated code looks up/loads symbols | Not a search path for `#include` |
| Explicit selection | `--include-function name`, `--include-struct name`, ... | Filters declarations to be generated as bindings | Does not modify the already-compiled C binary |
| List symbols | `--dump-includes file` | Generates a list of `--include-*` options that can be edited for filtering | Not a compiled Java API |
| Comments | `--copy-comments` (if supported by tool version) | Copies comments preceding declarations into generated docs | Does not change the ABI |

Three path layers are commonly confused:

```text
Header search time:  -I /opt/lib/include
Generation output:   --output generated
Native runtime:      --library :/opt/lib/libfoo.so
                      or --library foo with an appropriate OS search path
Java compile/runtime: --class-path classes
```

These paths serve **four different mechanisms**. Changing `-I` does not help the JVM find `libfoo.so` at runtime; changing `java.library.path` does not help Clang find `foo.h` when generating Java bindings.

## 3. Choose the right main header, not just the header containing the prototype you want to call

C libraries often have a public umbrella header such as:

```c
/* /opt/vendor/include/vendor/vendor.h */
#ifndef VENDOR_H
#define VENDOR_H

#include <vendor/types.h>
#include <vendor/config.h>
#include <vendor/api.h>

#endif
```

In real C code, compilers typically use:

```c
#include <vendor/vendor.h>
```

Therefore, `jextract` should also receive the **main public header** recommended by the library, rather than picking an internal `detail/private_impl.h` just because it contains a prototype.

Why?

1. The main header may set feature-switch macros and import types before declaring functions.
2. C has include guards, conditional compilation, typedef aliases, and structures that depend on `#include` order.
3. An internal header may not parse standalone: it may be missing a typedef, platform macro, or packing instruction.
4. Public headers are what the library commits to supporting; private headers may change between patch versions.
5. The root header alone is not enough if dependencies are found via `#include <vendor/...>`, so the right `-I` is still needed.

**C++ note:** `jextract` primarily parses the **C ABI from C headers**. C++ overloads, namespaces, templates, classes, and name mangling are not handled as a stable C API simply by passing a C++ header. To call a C++ library, provide a C-compatible wrapper:

```cpp
/* Illustrative wrapper header for a C++ library. */
#ifdef __cplusplus
extern "C" {
#endif

int widget_compute(int value);
void *widget_create(void);
void widget_destroy(void *widget);

#ifdef __cplusplus
}
#endif
```

Then generate bindings from the **C wrapper header**; all exported C functions must be implemented in the binary. Do not expect `jextract` to automatically translate C++ templates into Java generic classes.

## 4. Configuring `-I`/`--include-dir` and header search order

For example, `include/demo/api.h` has:

```c
#include <demo/build.h>
```

To parse it, the command needs a header search root such that `include/demo/build.h` exists:

```bash
jextract -I include include/demo/api.h
```

Or the long form:

```bash
jextract --include-dir include include/demo/api.h
```

In the example, `include` is the **root**, not `include/demo`, because the include directive has the `demo/` prefix. If you pass `-I include/demo`, Clang will look for something like `include/demo/demo/build.h` and may report file not found.

### Multiple include directories

```bash
jextract \
  -I vendor/sdk/include \
  -I project/include \
  -I generated/config/include \
  project/include/myproject/api.h
```

`-I` may appear multiple times; directories are searched in the order provided, following compiler/Clang lookup rules. **Order is part of the build configuration**, especially when two SDKs both contain a file named `config.h` or `types.h`.

Distinguish:

- `#include "local.h"` typically prioritizes paths relative to the including file before search directories, depending on compiler/target.
- `#include <library/foo.h>` is searched along include search paths/system paths.
- `-I vendor/sdk/include` does not mean `jextract` automatically picks every `.h` in that directory to generate bindings; it only helps parse **the headers actually included** through the translation unit.
- A header parsed as a dependency may bring in many unwanted declarations; use `--include-*` filters if you only want a small public surface.

### When paths contain spaces

Use shell quotes to prevent splitting the path:

```bash
jextract \
  --include-dir "/opt/vendor SDK/include" \
  --output "generated bindings" \
  "/opt/vendor SDK/include/vendor/api.h"
```

The quotes here are for the **shell**, not part of the directory name. On Windows PowerShell/cmd, escaping/quoting differs from Unix; use the appropriate command for your OS and print `jextract --help` to verify.

### Multiple main headers

`jextract` supports multiple headers as input; the documentation requires `--header-class-name` when there are multiple input headers, because a single name cannot be inferred from one file. Illustrative example:

```bash
jextract \
  --include-dir sdk/include \
  --header-class-name VendorApi \
  --target-package example.vendor \
  --output generated \
  sdk/include/vendor/core.h \
  sdk/include/vendor/io.h
```

This is a **sample** command; it requires the actual files and a valid include graph. For large projects, **a single umbrella header** recommended by the SDK is usually used to minimize preprocessing/ordering differences.

## 5. `-D`/`--define-macro` is C preprocessor configuration

C headers often use macros to decide which declarations exist:

```c
#ifndef LIB_ENABLE_FAST
#define LIB_ENABLE_FAST 0
#endif

int lib_normal(int value);

#if LIB_ENABLE_FAST
int lib_fast(int value);
#endif
```

Without `-D LIB_ENABLE_FAST=1`, the parser **does not see** the `lib_fast` prototype because the `#if` branch evaluates to false. When enabled:

```bash
jextract -D LIB_ENABLE_FAST=1 path/to/lib.h
```

Or:

```bash
jextract --define-macro LIB_ENABLE_FAST=1 path/to/lib.h
```

The preprocessor sees `LIB_ENABLE_FAST=1`, so the `lib_fast` prototype enters the set of extractable symbols.

### `#if` vs. `#ifdef`

```c
#if LIB_ENABLE_FAST
int fast_a(int);
#endif

#ifdef LIB_ENABLE_FAST
int fast_b(int);
#endif
```

- Macro not defined: `#if LIB_ENABLE_FAST` is treated as false (a compiler warning may occur when strict warnings are enabled); `#ifdef LIB_ENABLE_FAST` is false.
- `-D LIB_ENABLE_FAST=0`: `#if LIB_ENABLE_FAST` is **false**, but `#ifdef LIB_ENABLE_FAST` is **true**, because `#ifdef` checks for **existence**, not value.
- `-D LIB_ENABLE_FAST` without `=...`: according to the jextract docs, it defines the macro with value `1`.

Choose `-D` according to the library's own semantics, not just by looking at the macro name. If the header uses `#ifdef FEATURE`, `-DFEATURE=0` can still **enable the declaration branch**.

### Macros affect the ABI too, not just the number of functions

```c
#ifdef LIB_USE_WIDE_INDEX
typedef long long lib_index_t;
#else
typedef int lib_index_t;
#endif

int lib_read(lib_index_t index);
```

If the C binary was built with `LIB_USE_WIDE_INDEX` but jextract parses the header without that macro, the Java bindings may assume the argument is `int` while the C implementation expects `long long`. The result may be wrong or crash; this is an **ABI mismatch**, not just a missing-symbol error.

Therefore, macros that affect **type sizes, struct packing, alignment, calling convention, exported functions, and conditional declarations** must be synchronized across:

1. The build/configuration of the C library (or the ABI published by a prebuilt binary).
2. The `jextract` invocation.
3. The target OS/architecture of the Java program.

Do not enable a macro just so `jextract` sees more prototypes if the actual native library does not have the corresponding ABI/function.

### Command-line macros do not automatically become Java constants

This is an often-overlooked point. The `jextract` documentation explains: **only macro definitions encountered by the parser in header files are considered for generating constant accessors**. A macro supplied **only via `-D`** to control preprocessing **does not automatically get a Java getter** like `LIB_ENABLE_FAST()`.

For example:

```c
/* Header */
#define LIB_API_VERSION 7
```

`LIB_API_VERSION` is an **object-like constant macro in the header**, so jextract can generate `LIB_API_VERSION()` if the value type is supported and not excluded by filters. In contrast, `-D LIB_ENABLE_FAST=1` only creates a preprocessing symbol to select branches; it does not by default generate `LIB_ENABLE_FAST()` in Java.

Not every C macro becomes Java code. According to the `jextract` guide, direct support is mainly for **object-like macros** with numeric primitive, string, or pointer values that the tool can represent; **function-like macros** such as `#define MAX(a,b) ...` do not automatically generate an equivalent Java method. If you need a callable function, write a **real C wrapper function** or move simple logic to Java.

## 6. Declaration filters: select the exact API you want to generate

Main `jextract` options include:

| Option | C declaration kind selected | Example |
| --- | --- | --- |
| `--include-function NAME` | C function | `--include-function demo_add` |
| `--include-constant NAME` | Macro constant / enum constant recognized by the tool | `--include-constant DEMO_LEVEL` |
| `--include-struct NAME` | `struct` by tag/name | `--include-struct DemoPair` |
| `--include-union NAME` | `union` | `--include-union DataValue` |
| `--include-typedef NAME` | `typedef` alias | `--include-typedef demo_handle_t` |
| `--include-var NAME` | Global variable | `--include-var demo_counter` |

When **no** `--include-*` is used, the tool may generate bindings for many declarations in the input and parsed headers. When **any** include filter is present, symbols not matched by the filters are **excluded from the generated bindings**.

This lets a Java module expose only the needed part of the API. However, filters must account for **dependencies**: a function using a `struct`/`typedef`/callback type may need that type's binding. If you select a function but exclude a struct it depends on, jextract may report an error like “depends on ... which has been excluded” and stop generating.

**Example of selecting complete dependencies:**

```c
struct DemoPair {
    int left;
    int right;
};

int demo_pair_sum(const struct DemoPair *pair);
```

If you need a generated wrapper for `demo_pair_sum`, you should select **both**:

```bash
--include-function demo_pair_sum \
--include-struct DemoPair
```

`--include-typedef DemoPair` is not needed in this example because the declaration uses **`struct DemoPair`**, and there is no separate `typedef DemoPair`. If the actual header has `typedef struct ... Foo;`, check the actual symbols listed by jextract and select the corresponding kind and name.

### Using `--dump-includes` to find actual symbol names

Before designing an include list manually, you can run:

```bash
jextract \
  --include-dir include \
  --define-macro DEMO_ENABLE_EXTRA=1 \
  --define-macro DEMO_SCALE=3 \
  --dump-includes includes.txt \
  include/demo/api.h
```

`includes.txt` contains option lines such as:

```text
--include-struct DemoPair
--include-function demo_add
--include-function demo_scaled
--include-function demo_pair_sum
--include-constant DEMO_LEVEL
```

This is an **illustration of the relevant lines**, not a promise that the file contains only those five lines or in that exact order. `--dump-includes` output may include comments, source headers, and declarations from header dependencies. Actual output depends on jextract version, platform, preprocessing state, and input headers.

**Read the actual list** before filtering. Then save the selected list into an **argument file**, for example `selected-includes.txt`:

```text
--include-constant DEMO_LEVEL
--include-struct DemoPair
--include-function demo_add
--include-function demo_scaled
--include-function demo_pair_sum
```

Run command:

```bash
jextract @selected-includes.txt \
  -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  --target-package demo.binding \
  --header-class-name DemoNative \
  --output generated \
  --library ":$(pwd)/libdemoapi.so" \
  include/demo/api.h
```

`@argfile` is a repeatable way to organize configuration, convenient for code review/CI. If a symbol disappears due to macro/header changes, the generation step should **fail clearly** rather than silently continuing with a Java API missing functions.

### Do not confuse "export" in jextract with "export" in the C linker

- `--include-function demo_scaled`: allows generating a Java binding **if Clang actually sees the prototype**.
- `cc -shared ...` / native linker exports: determines whether `libdemoapi.so` has the `demo_scaled` symbol for FFM to find at runtime.
- A generated Java method **does not prove** that the corresponding dynamic symbol is exported.
- Conversely, if the C binary has the `demo_scaled` symbol but header `#if` does not bring the prototype into jextract's translation unit, the Java binding **is not generated**.

Therefore, you must check both **header preprocessing** and the **exported native symbol table**.

## 7. Complete lab: header paths, macros, and exporting only the selected API

This is an example **for Linux x86-64 with JDK 22+ and a matching jextract**. You will create a small C library with three functions:

- `demo_add(int,int)`: always declared and exported.
- `demo_scaled(int)`: only declared/compiled when `DEMO_ENABLE_EXTRA == 1`; result uses `DEMO_SCALE` from a macro.
- `demo_pair_sum(const struct DemoPair*)`: takes a C struct pointer; jextract must also generate a binding for `struct DemoPair`.

At the same time, the main header defines `DEMO_LEVEL 7` to illustrate including a **constant macro in the header file** instead of expecting a `-D` value to turn into a Java accessor on its own.

### File layout

```text
jextract-lab/
  include/
    demo/
      build.h
      api.h
  src/
    demoapi.c
  DemoMain.java
  generated/                 <- created by jextract
  classes/                   <- created by javac -d
  libdemoapi.so              <- created by cc
```

All commands below are run inside the `jextract-lab` directory. The `include/demo` and `src` directories must be created before saving the files.

### File 1 — `include/demo/build.h`

```c
#ifndef DEMO_BUILD_H
#define DEMO_BUILD_H

/* Default configuration if compiler/jextract does not pass -D. */
#ifndef DEMO_ENABLE_EXTRA
#define DEMO_ENABLE_EXTRA 0
#endif

#ifndef DEMO_SCALE
#define DEMO_SCALE 2
#endif

#endif
```

This file is a dependency header, **not the main API header**. Both macros can be overridden with `-D` when the compiler/jextract parses, because `#ifndef` only assigns a default value when the macro does not already exist.

### File 2 — `include/demo/api.h`

```c
#ifndef DEMO_API_H
#define DEMO_API_H

/* -I include allows finding <demo/build.h>. */
#include <demo/build.h>

/* Constant located in header; jextract can generate an accessor. */
#define DEMO_LEVEL 7

/* Named C struct, selected via --include-struct DemoPair. */
struct DemoPair {
    int left;
    int right;
};

/* Public API that always exists. */
int demo_add(int a, int b);

/* This prototype depends on a preprocessing macro. */
#if DEMO_ENABLE_EXTRA
int demo_scaled(int value);
#endif

/* Function depending on a C struct layout. */
int demo_pair_sum(const struct DemoPair *pair);

#endif
```

Meaning:

- `#include <demo/build.h>` requires `-I include`, because the root header `build.h` is at `include/demo/build.h`.
- `DEMO_LEVEL` is `#define`d in the **header file** and has an object-like numerical value `7`.
- `DEMO_ENABLE_EXTRA` uses `#if`, so `-D DEMO_ENABLE_EXTRA=1` is required to enable the `demo_scaled` prototype.
- `struct DemoPair` has two `int` fields and a pointer parameter in `demo_pair_sum`; Java needs the generated struct wrapper/layout to allocate memory correctly.
- There are no C++ constructs; the entire API has a clear C ABI.

### File 3 — `src/demoapi.c`

```c
#include <demo/api.h>

int demo_add(int a, int b) {
    return a + b;
}

#if DEMO_ENABLE_EXTRA
int demo_scaled(int value) {
    return value * DEMO_SCALE;
}
#endif

int demo_pair_sum(const struct DemoPair *pair) {
    if (pair == 0) {
        return -1; /* Illustrative sentinel when pointer is null. */
    }
    return pair->left + pair->right;
}
```

In the demo, addition/multiplication use small numbers intentionally so as not to overflow C signed `int`. The C code does not `malloc` and does not retain the struct pointer after the call; Java allocates the struct in an arena with a valid lifetime.

### Step A — compile the native shared library

```bash
mkdir -p generated classes

cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  -o libdemoapi.so src/demoapi.c
```

**Important configuration:** The C library is compiled with `DEMO_ENABLE_EXTRA=1` so it **exports `demo_scaled`**, and with `DEMO_SCALE=3` so `demo_scaled(4) == 12`.

Check symbol exports (Linux):

```bash
nm -D --defined-only libdemoapi.so
```

The list still depends on the compiler/linker, but the symbols `demo_add`, `demo_scaled`, and `demo_pair_sum` must be found. Do not expect a dynamic symbol `DEMO_LEVEL`, because that is a **preprocessor constant**, not a C function or global variable.

### Step B — generate Java bindings with the right macros and filters

```bash
jextract --version

jextract \
  --include-dir include \
  --define-macro DEMO_ENABLE_EXTRA=1 \
  --define-macro DEMO_SCALE=3 \
  --output generated \
  --target-package demo.binding \
  --header-class-name DemoNative \
  --library ":$(pwd)/libdemoapi.so" \
  --include-constant DEMO_LEVEL \
  --include-struct DemoPair \
  --include-function demo_add \
  --include-function demo_scaled \
  --include-function demo_pair_sum \
  include/demo/api.h
```

**Exact explanation of each part:**

1. `include/demo/api.h` is the main public header of the example.
2. `--include-dir include` lets Clang parse the `<demo/build.h>` dependency.
3. `--define-macro DEMO_ENABLE_EXTRA=1` makes `#if DEMO_ENABLE_EXTRA` true, so `demo_scaled` appears in jextract's **header view**.
4. `--define-macro DEMO_SCALE=3` synchronizes the macro used when compiling the implementation. This macro only affects preprocessing; there will not necessarily be a Java accessor `DEMO_SCALE()` because it is **not** `#define`d in the header when a `-D` value is already present.
5. `--include-constant DEMO_LEVEL` generates a binding for the constant defined in `api.h` (accessible via an accessor such as `DEMO_LEVEL()`).
6. `--include-struct DemoPair` creates the wrapper/layout for C `struct DemoPair`; omitting it when a function needs the struct risks a missing dependency.
7. The three `--include-function` options restrict Java bindings to the exact three C functions needed.
8. `--target-package demo.binding` sets the Java namespace.
9. `--header-class-name DemoNative` sets a stable Java header/root class name instead of deriving `api_h` from the filename.
10. `--output generated` specifies the root directory for the Java files.
11. `--library ":$(pwd)/libdemoapi.so"` uses a leading `:` in the library value so `jextract` treats the rest as a **shared library path**, not a logical library name. `$(pwd)` is expanded by the Linux shell to the absolute directory when running the command, helping the generated binding load that exact file.

**Note:** `--library` does not change which declarations are parsed; it affects how generated bindings look up/load native symbols at runtime. If you only generate code from headers without a binary, `--library` may not be needed at generation time, but the final application must still configure appropriate library lookup.

### Step C — inspect generated Java files

```bash
find generated -type f -name '*.java' -print
```

With the configuration above, you should see generated sources under `package demo.binding`, including the header class `DemoNative` and struct binding `DemoPair` (helper file names/structure may differ across `jextract` versions). Expect entry points like:

```java
// SIMULATION of the API structure, not a copy of the exact generated source.
package demo.binding;

public class DemoNative {
    public static int DEMO_LEVEL() { /* ... */ }
    public static int demo_add(int a, int b) { /* ... */ }
    public static int demo_scaled(int value) { /* ... */ }
    public static int demo_pair_sum(
            java.lang.foreign.MemorySegment pair) { /* ... */ }
}

public class DemoPair {
    public static java.lang.foreign.MemorySegment allocate(
            java.lang.foreign.SegmentAllocator allocator) { /* ... */ }
    public static void left(
            java.lang.foreign.MemorySegment segment, int value) { /* ... */ }
    public static void right(
            java.lang.foreign.MemorySegment segment, int value) { /* ... */ }
}
```

**This is pseudocode of method shapes/names**, not a directly compilable Java file: Java does not allow two public top-level classes in one source file, and the bodies are generated by jextract. **Do not hand-edit generated code** based on the simulation; open the actual `generated/.../DemoNative.java` and `DemoPair.java` to verify the names/methods produced by your version of the tool. The OpenJDK guide describes a similar generated header class and struct wrapper mechanism.

### File 4 — `DemoMain.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

import demo.binding.DemoPair;
import static demo.binding.DemoNative.*;

public final class DemoMain {
    public static void main(String[] args) {
        System.out.println("level=" + DEMO_LEVEL());
        System.out.println("add=" + demo_add(2, 5));
        System.out.println("scaled=" + demo_scaled(4));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment pair = DemoPair.allocate(arena);
            DemoPair.left(pair, 8);
            DemoPair.right(pair, 11);
            System.out.println(
                    "pair=" + demo_pair_sum(pair));
        }
    }
}
```

Java allocates the struct via `Arena.ofConfined()`; `DemoPair.allocate(arena)` uses the exact C struct layout generated by jextract from the header. `DemoPair.left(pair, 8)` and `right(pair, 11)` are setters. The C function borrows the pointer **only during the synchronous call** and does not retain it after returning; closing the arena afterward is valid.

**Do not write `new DemoPair(...)`**: generated struct wrappers typically operate on a `MemorySegment` with ABI-defined layout/offsets rather than acting like a Java POJO with independent fields.

### Step D — compile/run Java

```bash
javac -d classes \
  $(find generated -type f -name '*.java') \
  DemoMain.java

java --enable-native-access=ALL-UNNAMED \
  -cp classes \
  DemoMain
```

`--enable-native-access=ALL-UNNAMED` applies when the app and generated bindings are in the unnamed module/classpath; when the application is in a named module, grant native access to that module. Generated jextract sources use FFM restricted calls to perform native downcalls/library lookup.

On a jextract/JDK toolchain compatible with the guide, **expected stdout**:

```text
level=7
add=7
scaled=12
pair=19
```

Arithmetic check:

- `DEMO_LEVEL` is defined as `7` in `api.h`.
- `demo_add(2,5) = 7`.
- The native binary is compiled with `DEMO_SCALE=3`; `demo_scaled(4) = 4 × 3 = 12`.
- `DemoPair` has `left = 8`, `right = 11`; C `demo_pair_sum` returns `8 + 11 = 19`.

All numbers above depend on **the exact same headers/macros/library binary provided**. If a jextract version changes the shape of generated wrappers, use `jextract --version`/`--help`, read the generated code, and adjust the Java call site to match the actual generated API rather than forcing generated classes back to old assumptions.

## 8. Three intentional experiments to see the meaning of flags clearly

### Experiment 1 — omit `-I include`

```bash
jextract \
  -D DEMO_ENABLE_EXTRA=1 \
  --output generated-no-include \
  include/demo/api.h
```

Because `api.h` contains `#include <demo/build.h>`, the tool may report something like `'demo/build.h' file not found` or a dependency parse error. Use `-I include`, **not** `-I include/demo`, so Clang has the right header search root.

If a machine happens to have a header with the same name in a system include path, the build may accidentally parse the **wrong header version**. Thus, this test is only illustrative; in production, pin the SDK include root and verify which source header was parsed, rather than only checking the tool exit code.

### Experiment 2 — omit `-D DEMO_ENABLE_EXTRA=1`

```bash
jextract \
  -I include \
  --dump-includes without-extra.txt \
  include/demo/api.h
```

In `build.h`, the default is `DEMO_ENABLE_EXTRA=0`. Since `#if DEMO_ENABLE_EXTRA` is false, the `demo_scaled` prototype is removed during preprocessing, so the symbol list does not contain this function. If you then try to request `--include-function demo_scaled`, the tool cannot generate a valid binding for a function that **does not exist in the translation unit**.

Conversely, if the C binary was compiled with the feature ON but the Java code was generated with the feature OFF, you will have a native symbol that the Java binding does not expose. If the feature is OFF in the native binary but ON when jextract parses, the generated Java has the method, but native lookup at call time may report a missing symbol.

### Experiment 3 — filter out a required struct dependency

```bash
jextract \
  -I include \
  --include-function demo_pair_sum \
  --output generated-missing-type \
  include/demo/api.h
```

`demo_pair_sum` takes `const struct DemoPair *`. Under jextract's filtering mechanism, if the struct is excluded while the function depends on it, the tool may stop with a dependency error (depending on tool version and type form). Do not try to work around it by passing an arbitrary `long` address in Java. Add `--include-struct DemoPair` and regenerate the bindings.

**Filtering rule:** select APIs by **dependency closure** (the required types/constants/layouts), not only by the names of functions Java will call.

## 9. `--dump-includes`, `@argfile`, and repeatable configuration

For large SDKs, running `jextract` without filters can generate thousands of Java classes/methods. An overly large API surface:

- Makes generated code hard to review.
- Increases compile cost and alters the dependency graph.
- Accidentally pulls internals into the Java module.
- Increases the risk of code churn when the SDK updates.
- When headers contain platform-specific types, may produce unused Java APIs that still need resolution.

A consistent workflow:

```text
1. Choose the right SDK version and umbrella header
2. Lock compiler target, -I roots, -D switches
3. jextract --dump-includes symbols.txt ...
4. Select required functions / constants / structs / typedefs
5. Save selected includes in @argfile (code-reviewed)
6. jextract @argfile with the same -I/-D/package/library
7. Compile generated Java
8. Test native calls + binary ABI
9. Commit generated sources and toolchain configuration per project policy
```

Using `@argfile` to separate the symbol list from the build script helps review API changes when the library upgrades: a disappearing function or a changed typedef can be caught early.

One subtle point: **command-line macros do not automatically become accessors**, whereas macros in headers can generate Java constants if jextract supports the value type. If you want Java code to have a stable constant API, prefer a **named enum/object-like constant definition in the public header**, or a C function like `int lib_api_version(void)` if the value must be determined at runtime. Do not use `-D` as a "Java constant generator".

## 10. Layered debugging: header, preprocess, bindings, and runtime errors

When `jextract` or the Java app fails, diagnose at the **right layer**:

| Symptom | Layer | Likely cause | Check/fix |
| --- | --- | --- | --- |
| `fatal error: demo/build.h: No such file or directory` | Parse/header | Wrong `-I` root, header path/SDK | Verify `include/demo/build.h` exists, add `-I include` |
| `unknown type name` | Preprocess/dependency | Missing header, macro excludes typedef, wrong include order | Use main header, sync `-D`, check preprocessed text |
| `demo_scaled` missing in generated Java | Preprocess/filter | `DEMO_ENABLE_EXTRA` false, or missing `--include-function` | `--dump-includes` with the right `-D`, then add filter |
| `DemoPair` not generated | Filter/dependency | Missing `--include-struct DemoPair` | Select the type closure, not only the function |
| `DEMO_SCALE=3` seen during C compile but no Java `DEMO_SCALE()` | Constant generation | Macro only set via `-D`; not a header definition | If you want a constant, declare it compatibly in the public header |
| Generated Java missing `DEMO_LEVEL()` | Filter/macro | Unsupported macro type, macro not seen, or missing include-constant | Check `--dump-includes`, header, and jextract version |
| `UnsatisfiedLinkError`/symbol not found | Runtime lookup | Wrong `--library`, binary does not export symbol, C feature macro OFF | `nm -D`, check `LD_LIBRARY_PATH`/absolute library |
| Java compile reports package/class does not exist | Java compile | Wrong `--output`/`-t`, forgot to compile generated files | `find generated`, `javac -d classes ...`, classpath |
| JDK reports native access error | FFM restricted access | Missing `--enable-native-access` for the right module | Add flag per JDK/unnamed/named module |
| JVM crashes or returns nonsense numbers | ABI | Header differs from binary, struct packing, C `long` width, calling convention | Compare SDK+target macros+layouts, use sanitizers |
| Java runs on Linux but fails on Windows | Platform | Different OS search/ABI/packing/`long` | Generate/test bindings per target OS/arch |
| C library compiles but jextract does not run | Toolchain | jextract not installed, missing native libclang, JDK/tool version mismatch | `jextract --version`/`--help`, install matching release |
| Function-like macro does not become Java method | Generator support | Not directly supported by jextract | Write an exported C wrapper function or Java helper |
| Accessing memory after `Arena.close` | Lifetime | Buffer/native pointer retained past expiration | Fix owner/lifetime, do not keep pointer once arena closes |

**Note:** An `UnsatisfiedLinkError` can arise either because the shared library itself failed to load or because the native function symbol was not found. Read the message and native loader diagnostics instead of immediately blaming `-I`.

### Using the C compiler to inspect preprocessing

To check which C branch is actually active:

```bash
cc -E -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  src/demoapi.c > preprocessed.c

grep -n 'demo_scaled' preprocessed.c
```

This is a helper technique to cross-check **the same macro/header config**; it does not replace actual output from Clang/jextract if the compiler/target differs. Do not commit `preprocessed.c` to the source tree unless there is a special reason, as it is very large and environment-dependent.

To view active macro definitions (supported by GCC/Clang):

```bash
cc -dM -E -I include \
  -D DEMO_ENABLE_EXTRA=1 \
  -D DEMO_SCALE=3 \
  include/demo/api.h | grep 'DEMO_'
```

Expect macros such as `DEMO_ENABLE_EXTRA 1`, `DEMO_SCALE 3`, and `DEMO_LEVEL 7`. A macro appearing in preprocessing output **does not mean** jextract must generate a Java accessor for it.

### Checking actual native symbol exports

```bash
nm -D --defined-only libdemoapi.so |
  grep -E 'demo_add|demo_scaled|demo_pair_sum'
```

If `demo_scaled` is missing, check whether the `cc` command has `-D DEMO_ENABLE_EXTRA=1`. If a function is declared `static` in C source, it has **internal linkage** and generally cannot be found via dynamic symbol lookup; a real exported C API is required. If the project builds with `-fvisibility=hidden`, add the platform-appropriate export attribute so public functions are visible.

### Inspecting generated Java instead of guessing

```bash
grep -R 'demo_scaled' generated
grep -R 'class DemoPair' generated
grep -R 'DEMO_LEVEL' generated
```

These search commands are only for debugging **the lab's generated Java**; they do not replace opening the source code to review the ABI. Generated files may have multiple helper classes and metadata depending on version; if package names or signatures change, consult the actual guide/release.

## 11. Filtering declarations by actual type kind

### Functions

`--include-function NAME` requires a C function that has a **declaration visible to the parser**. If the header only has a macro `#define CALL(x) do_work(x)` without a `CALL` prototype, you cannot use `--include-function CALL` and expect a corresponding C function downcall to be generated. A Java downcall needs a **callable native symbol**, not a macro that the C preprocessor erases/expands.

### Structs/Unions

`--include-struct NAME` / `--include-union NAME` select C aggregate types. C layout depends on alignment, packing, compiler ABI, and conditional fields; in production, verify `sizeof`, offsets, and binary version. A field changed from `int` to `long` via a macro can make the generated Java layout wrong if the C build and jextract are out of sync.

### Typedefs

`--include-typedef NAME` selects aliases, especially important when a C API uses opaque handles or function-pointer typedefs. A typedef such as `typedef struct Opaque Opaque;` can represent an incomplete type passed only by pointer; do not treat the Java segment as a struct value with an unknown layout. Understand the `create/destroy` ownership API instead of trying to dereference opaque memory.

### Constants

`--include-constant NAME` selects object-like macros/enum constants recognized by the parser. C enum values can be generated as Java accessors; C function-like macros do not automatically become callable functions. Some floating, string, and pointer constants have representations other than primitive integers; open the generated source rather than always assuming `int`.

### Global variables

`--include-var NAME` is for exported global variables declared by public headers, though C `static`/thread-local globals or symbols with hidden visibility may not resolve at runtime. Accessing C global native memory requires thread safety and proper lifetime. Do not confuse a global variable declaration with a `#define` macro constant.

### Callback typedefs and nested dependencies

If a function takes a C function-pointer typedef, the generator may need a generated functional interface/helper for the callback ABI. Filtering the function while forgetting the typedef can cause a missing dependency. A Java callback is converted by FFM into an upcall stub in an arena with an explicit lifetime; you do not only need the function name in `--include-function`.

## 12. Choosing `--library` and how the library is loaded at runtime

### Logical name

```bash
jextract --library demoapi \
  --output generated \
  --target-package demo.binding \
  -I include \
  include/demo/api.h
```

The name `demoapi` is mapped by the platform, typically `libdemoapi.so` on Linux. Generated code uses library lookup according to the tool and OS search mechanism. At runtime, the library may need to be on paths searched by the OS dynamic loader.

### Specific path

```bash
jextract --library ":/absolute/path/libdemoapi.so" \
  --output generated \
  -I include \
  include/demo/api.h
```

The `:` prefix makes the library specifier be interpreted as a **path** instead of a logical library name. This is easy to reproduce in a lab, but hardcoding an absolute path in **generated bindings** is unsuitable for applications distributed to other machines. In CI/production, consider a logical library name, loader configuration, or a mechanism to copy/package versioned native libs.

### `--use-system-load-library` is another option

According to the OpenJDK jextract guide, the `--use-system-load-library` option makes generated code load libraries from `-l` via `System.loadLibrary`/`System.load` using the JNI library loading mechanism. In that case `java.library.path` applies, though the library's own native dependencies may still be resolved by the OS loader using its own search paths.

**Do not mix path directives:** `-I` is for C headers, `--library` is for the native binary, and `-cp`/`--class-path` is for Java classes. They solve three different needs.

## 13. When upgrading an SDK or changing platforms

`jextract` generates code that depends on **how C headers are parsed at generation time**. Upgrading an SDK is not just copying a new `.so` file if the ABI changed.

A reliable update process:

1. Pin the **header version**, **native binary version**, **compiler target**, **jextract release**, and **JDK version**.
2. Save/verify the list of `-I` search roots, `-D` feature switches, and `--include-*` filters.
3. Regenerate bindings in an environment compatible with the target OS/architecture.
4. Compare generated sources with the previously reviewed version: functions, constants, structs, field offsets, carrier types.
5. Build the C binary with the same feature macros/ABI.
6. Compile Java and run smoke tests against real native symbols.
7. Run negative-path tests (missing feature, missing library, null pointers, lifetime/arena).
8. For structs/pointers/ownership, also check type sizes, alignment, target ABI, and concurrency.
9. Deploy only when headers/binary/generated Java form a **compatible set**.

Especially for C `long`: on common 64-bit Linux, `long` is 64-bit; on common 64-bit Windows, `long` is 32-bit. Struct layouts can differ even though the Java code has the same method names. Do not ship a single platform-specific binding across all OSes without verification.

A Java line `import static demo.binding.DemoNative.*;` looks like pure Java, but **part of the contract underneath is a native ABI**; treat generated bindings as a code boundary with higher risk than ordinary Java.

## 14. Pre-generation and release review checklist

- [ ] Selected the right **main public C header** of the SDK, not mistakenly pointing to an internal header.
- [ ] Confirmed `-I` roots for all transitive `#include`s, accounting for order and paths with spaces.
- [ ] `-D` on jextract matches the build/native binary, especially macros affecting **ABI**, packing, and conditional declarations.
- [ ] Distinguished `#if FEATURE` from `#ifdef FEATURE`; did not use `-DFEATURE=0` if the goal is to make `#ifdef FEATURE` false.
- [ ] Understood that `-D` macros are preprocessing-only; object-like macros in headers can become Java constants when supported; function-like macros are not generated as functions.
- [ ] Ran `--dump-includes` to learn the exact names/kinds of symbols.
- [ ] Filters include all functions, constants, struct/union/typedef dependencies, and global variables actually needed.
- [ ] Did not assume a selected function is an exported C symbol; checked `nm`/linker map on the actual binary.
- [ ] Pinned `--target-package`, `--header-class-name`, and `--output` so generated Java is stable.
- [ ] `--library`/OS loader paths and Java classpath are configured independently from header search paths.
- [ ] Chose a **JDK-compatible** jextract release (FFM final JDK 22+); verified `jextract --version`/`--help`.
- [ ] When using restricted FFM, configured `--enable-native-access` for the right named/unnamed module.
- [ ] Compiled generated Java sources and made real calls into the C library with at least one struct/pointer API.
- [ ] Verified ownership, Arena lifetime, native pointers, and deallocators (jextract does not handle these automatically).
- [ ] CI detects drift when SDK/headers/macros change; do not hand-edit generated files and skip regeneration.
- [ ] For multiple OS/arch targets, generate and test bindings for each supported target.

## 15. Self-check questions

**Question 1.** Is `-I include/demo` appropriate when `api.h` writes `#include <demo/build.h>` and the file is at `include/demo/build.h`?

**No.** The appropriate root is `-I include`. With `-I include/demo`, Clang may search a wrong path like `include/demo/demo/build.h`.

**Question 2.** If the C binary is compiled with `DEMO_ENABLE_EXTRA=0` but jextract uses `-D DEMO_ENABLE_EXTRA=1`, is there a problem?

Yes. jextract will see the `demo_scaled` prototype and generate a Java binding; the binary may **not export this symbol**. Calling the generated Java method may fail during symbol lookup (or during class/helper initialization). This is a mismatch between the header view and the actual binary.

**Question 3.** Does `-D DEMO_SCALE=3` guarantee the generated Java has a `DEMO_SCALE()` method?

**No.** `-D` defines a macro during preprocessing; according to the jextract guide, command-line-only macros do not automatically generate Java accessors. An object-like `#define` macro in a header of a supported type is a candidate for a constant accessor.

**Question 4.** Why must `--include-struct DemoPair` be selected along with `--include-function demo_pair_sum`?

Because the function depends on the layout of `struct DemoPair`. When filters are enabled, excluding a required type can leave the generated binding missing a dependency; jextract may report an error and stop. Select APIs by **dependency closure**.

**Question 5.** Does `--include-function demo_add` cause `demo_add` to be exported in `libdemoapi.so`?

**No.** It only selects a C declaration for generating a Java binding. Exports are determined by the C compiler/linker and visibility.

**Question 6.** If a header has `#define MULTIPLY(x,y) ((x)*(y))`, can `--include-function MULTIPLY` be used to generate a JNI/FFM downcall?

**No.** This is a **function-like preprocessor macro**, not a callable native function symbol; jextract does not automatically generate an equivalent Java function. Create an exported C wrapper function or a Java helper.

**Question 7.** Can `-D FEATURE=0` be used to disable every branch guarded by the FEATURE macro?

No. `#if FEATURE` is false, but `#ifdef FEATURE` is true. You must read the header's conditional implementation before choosing how to enable/disable it.

**Question 8.** Why is `--header-class-name` needed when there are multiple input headers?

According to the jextract guide, when there are multiple main headers, the tool requires a specific Java header/root class name. With a single header, this option can be used to stabilize the API instead of letting the tool derive it from the filename.

**Question 9.** The native library is at `/opt/lib/libdemoapi.so` and Java cannot load it. Does adding `-I /opt/lib` help?

No. `-I` only resolves header includes at generation time. Runtime needs the right `--library`/dynamic loader paths (or `--use-system-load-library` with `java.library.path`), not a C header path.

**Question 10.** Does a Java binding compiling successfully mean the C ABI is definitely right?

No. The Java compiler does not verify actual C struct layouts, native symbols, macro build flags, or calling conventions in the binary. Only running native integration tests on the target OS/architecture and checking the ABI can confirm it.

**Question 11.** When should `--dump-includes` + `@argfile` be used instead of manually typing 60 flags?

When the SDK is large, has many declarations, and needs a reviewed allowlist that is reproducible across machines. `--dump-includes` provides the actual names/kinds after preprocessing; `@argfile` stores the filter list, though the same `-I`/`-D`/tool versions are still required.

**Question 12.** Can a C++ template header be passed directly to jextract to generate Java bindings for all C++ overloads?

You should not. The tool works with C headers/C ABI; create a C wrapper API with `extern "C"` and explicit functions/types, then generate Java bindings from the wrapper.

## 16. Official documentation

- OpenJDK Code Tools — [jextract Guide: Running jextract, macros, filtering, command-line reference, library loading](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md).
- Dev.java — [Generate Java Bindings with Jextract: -I/-D, -l, -t, --dump-includes, and --include-*](https://dev.java/learn/ffm/jextract/).
- OpenJDK — [jextract repository and download/build instructions](https://github.com/openjdk/jextract).
- Oracle Java 22 — [Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html).
- OpenJDK — [JEP 454: Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454).
- GCC — [Preprocessor Options -D, -I, and conditional compilation](https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html).

**Remember:** `jextract` does not choose header paths, ABI macros, or the C API subset to generate on your behalf. **Choose the right main header**, configure `-I` so Clang finds all dependencies, use `-D` matching the library build, inspect symbols with `--dump-includes`, and filter with `--include-*` along with dependent types. Finally, verify the generated Java against the **actual native binary** and run FFM integration tests on the right platform.
