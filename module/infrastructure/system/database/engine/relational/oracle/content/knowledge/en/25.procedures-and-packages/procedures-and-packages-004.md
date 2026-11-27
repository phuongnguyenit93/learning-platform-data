# Scope of NOCOPY and Parameter Handling When Errors Occur

In PL/SQL, OUT and IN OUT parameters may need to copy data between the formal parameter and the actual parameter when calling a procedure or function. For records, collections, or large data structures, copying can consume significant time and memory. The **NOCOPY** keyword is a compiler hint to pass the parameter by reference, which can reduce copying overhead.

NOCOPY has an important impact when a program raises an exception. If the compiler actually passes by reference, modifications the procedure has already made to the parameter can directly affect the caller's variable, even when an exception escapes. With standard copy semantics, copy-out of OUT/IN OUT only happens when the subprogram terminates normally; if an exception is unhandled internally and propagates to the caller, values modified inside the formal parameter are not copied back via the standard mechanism.

Key point: **NOCOPY is only a compiler hint, not a guarantee that the parameter will always be passed by reference.** Therefore, code must be correct both when the compiler applies the hint and when the compiler ignores it. Never rely on NOCOPY definitely preserving or definitely reverting changes upon error.

## 1. Formal Parameter and Actual Parameter

When calling a procedure, the parameter declared in the procedure definition is called the formal parameter. The variable or expression passed at the call site is the actual parameter.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE add_tax (
    p_amount IN OUT NUMBER
) AS
BEGIN
    p_amount := p_amount * 1.08;
END;
/

DECLARE
    l_amount NUMBER := 100;
BEGIN
    add_tax(l_amount);
    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

In the example:

- P_AMOUNT is the formal parameter.
- L_AMOUNT is the actual parameter.
- The procedure modifies the formal parameter; after the procedure finishes normally, the result is returned to the caller's variable according to IN OUT mode.

## 2. The Three Parameter Modes: IN, OUT, and IN OUT

Before examining NOCOPY, it is necessary to understand the purpose of each mode:

| Mode | Passes Data Into Subprogram | Returns Data to Caller | Assignable Inside Subprogram? |
|---|---|---|---|
| IN | Yes | Not via parameter contract | No; parameter is read-only |
| OUT | Does not take actual's initial value as input data | Yes | Yes |
| IN OUT | Yes | Yes | Yes |

### 2.1 IN

IN is used when the subprogram only needs to read data:

~~~sql
CREATE OR REPLACE PROCEDURE print_amount (
    p_amount IN NUMBER
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(p_amount);
END;
/
~~~

IN parameters are not the target of NOCOPY. NOCOPY is used with OUT and IN OUT.

### 2.2 OUT

OUT is used when the subprogram produces a value to return:

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_count (
    p_count OUT PLS_INTEGER
) AS
BEGIN
    SELECT COUNT(*)
    INTO p_count
    FROM employees;
END;
/
~~~

A formal OUT parameter does not use the actual's existing value as input. The subprogram must assign a value before the caller uses the result.

### 2.3 IN OUT

IN OUT is used when the subprogram receives a current value, processes it, and returns a new value:

~~~sql
CREATE OR REPLACE PROCEDURE apply_discount (
    p_amount IN OUT NUMBER
) AS
BEGIN
    p_amount := p_amount * 0.90;
END;
/
~~~

The actual's initial value is used as input; the new value is returned to the caller when the subprogram completes normally.

## 3. Pass by Value vs. Pass by Reference

Two concepts to distinguish:

- **Pass by value / copy semantics:** the subprogram works on a copy. On normal return, the OUT or IN OUT value is copied back to the actual parameter.
- **Pass by reference:** the formal parameter directly references the storage of the actual parameter. Modifications through the formal parameter can directly affect the actual parameter.

Copy model:

~~~text
Caller variable
      |
      | copy-in (IN OUT)
      v
Formal parameter copy
      |
      | subprogram modifies copy
      v
Formal parameter result
      |
      | copy-out on normal return
      v
Caller variable updated
~~~

Reference model:

~~~text
Caller variable <-------------------+
      ^                              |
      |                              |
      +---- Formal parameter --------+
                |
                v
          Subprogram writes
          directly to caller data
~~~

This is a conceptual model to understand behavior. How the compiler implements it in practice depends on data types, actual arguments, call context, and optimization conditions.

## 4. What Is NOCOPY?

NOCOPY is a hint placed on an OUT or IN OUT parameter. The hint asks the PL/SQL compiler to pass the parameter by reference if possible, instead of creating a full copy.

Syntax:

~~~sql
PROCEDURE process_items (
    p_items IN OUT NOCOPY t_item_table
);
~~~

Package declaration example:

~~~sql
CREATE OR REPLACE PACKAGE item_api AS
    TYPE t_item_table IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    PROCEDURE increase_values (
        p_items IN OUT NOCOPY t_item_table
    );
END item_api;
/
~~~

The package body declares the same mode and NOCOPY:

~~~sql
CREATE OR REPLACE PACKAGE BODY item_api AS
    PROCEDURE increase_values (
        p_items IN OUT NOCOPY t_item_table
    ) AS
    BEGIN
        FOR i IN 1 .. p_items.COUNT LOOP
            p_items(i) := p_items(i) + 1;
        END LOOP;
    END increase_values;
END item_api;
/
~~~

NOCOPY does not change the business semantics of OUT or IN OUT mode. It hints to the compiler how to pass data so copying may be avoided.

### 4.1 NOCOPY Is Not a Data Type

NOCOPY is not a data type, not a constraint, and not a transaction option. It is a hint on a parameter declaration.

Types commonly considered:

- Collections with many elements.
- Nested tables or associative arrays.
- Large VARRAYs.
- Records with many fields or large field types.
- PL/SQL structures with significant copy overhead.

For small scalars like NUMBER or short VARCHAR2, the benefit is usually negligible. Only add NOCOPY when measurements show parameter-passing overhead needs optimization.

## 5. Why Can NOCOPY Improve Performance?

Suppose a procedure receives a collection containing hundreds of thousands of elements:

~~~sql
TYPE t_number_table IS TABLE OF NUMBER
    INDEX BY PLS_INTEGER;
~~~

If every call had to copy the entire collection, the cost could include:

- Allocating memory for the copy.
- Copying each element.
- Copying the result back to the caller when the procedure finishes.
- Increased memory pressure when many sessions call concurrently.

If NOCOPY is applied by the compiler, the procedure can operate directly on the caller's data, eliminating one or more copies.

However:

- There is no guarantee that the hint will always be applied.
- Not every large parameter is passed by reference in every situation.
- NOCOPY does not reduce loop iterations or algorithmic cost inside the procedure.
- Benefits must be measured on real data, versions, and workloads.

## 6. NOCOPY Is a Hint That the Compiler Can Ignore

The most important contractual point is that the compiler may choose not to apply NOCOPY. When pass-by-reference cannot be done safely or data conversion is needed, the compiler may fall back to copy semantics.

Situations that may prevent the hint from being applied include:

- Actual and formal types require data conversion.
- The actual argument or calling method does not allow safe direct referencing.
- Call context or data type characteristics force the compiler to create a temporary.
- Certain cases of passing parameters across remote/distributed call boundaries.

The exact list of conditions depends on version and context; these examples should not be treated as an exhaustive list.

There is no SQL% attribute or simple PL/SQL runtime flag to ask "did the compiler apply NOCOPY on this call?". Sound design must remain valid under both implementations.

### 6.1 Do Not Write Logic Depending on NOCOPY Definitely Taking Effect

Suppose a caller expects its variable to always retain partial changes when a procedure fails because NOCOPY was declared. This is unsafe: if the compiler ignored the hint, the actual may not receive uncopied changes when an exception escapes.

Conversely, if a caller assumes an exception always leaves the actual untouched because OUT/IN OUT parameters are copied, the code can break when the compiler applies NOCOPY and writes directly to the actual.

Define the exception contract independently of whether the compiler applies the hint.

## 7. Scope of NOCOPY on Normal Subprogram Termination

When a subprogram terminates normally:

- OUT returns the result to the actual.
- IN OUT returns the updated value to the actual.
- If NOCOPY was applied, changes may have already acted directly on the actual during execution.
- If NOCOPY was ignored, the compiler can perform copy-out via the standard mechanism.

For the caller, the final outcome upon normal return is still the data returned by the procedure according to the OUT/IN OUT contract.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE add_bonus (
    p_salary IN OUT NOCOPY NUMBER
) AS
BEGIN
    p_salary := p_salary + 1000;
END;
/

DECLARE
    l_salary NUMBER := 20000;
BEGIN
    add_bonus(l_salary);
    DBMS_OUTPUT.PUT_LINE(l_salary);
END;
/
~~~

After the procedure terminates normally, the caller receives the value 21000.

## 8. Parameters When Exceptions Occur

This is where NOCOPY most noticeably affects program behavior.

### 8.1 OUT/IN OUT with Standard Copy Semantics

With copy-based passing:

1. The OUT/IN OUT formal parameter is processed by the subprogram in its own storage.
2. The subprogram may modify the formal parameter.
3. If the subprogram terminates normally, the value is copied out to the actual.
4. If an exception is unhandled inside and propagates to the caller, normal copy-out does not occur.

For IN OUT, the caller's actual retains its pre-call value if an exception escapes and copy-out does not occur. For OUT, the caller does not receive a new result from the failed call.

### 8.2 When NOCOPY Is Applied

If the compiler applies NOCOPY, the formal parameter references the actual directly. Modifications already made may already appear in the caller's variable before the subprogram ends.

If an exception then occurs and escapes:

- Direct modifications already written may remain in the actual.
- PL/SQL does not automatically restore the caller variable's original value.
- The caller must have a recovery strategy if the contract requires unchanged state on error.

### 8.3 Comparison Table

| Scenario | OUT/IN OUT with Copy Semantics | OUT/IN OUT When NOCOPY Is Applied |
|---|---|---|
| Subprogram returns normally | Copies result back to actual | Changes already applied directly; caller sees result |
| Exception handled internally and subprogram returns normally | Current result is copied out | Direct changes remain in actual unless code restores them |
| Exception unhandled and propagates to caller | No copy-out of the call's result | Directly written changes may remain |
| Compiler ignores NOCOPY | Behaves like copy semantics | Reference passing must not be assumed |

Because the compiler can ignore the hint, applications must not rely on a single column of this table as a guarantee for every call marked NOCOPY.

## 9. Collection Example: Failure After Partial Modification

Create a package:

~~~sql
CREATE OR REPLACE PACKAGE nocopy_demo AS
    TYPE t_values IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    PROCEDURE change_then_fail (
        p_values IN OUT NOCOPY t_values
    );
END nocopy_demo;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY nocopy_demo AS
    PROCEDURE change_then_fail (
        p_values IN OUT NOCOPY t_values
    ) AS
    BEGIN
        p_values(1) := p_values(1) + 100;
        p_values(2) := p_values(2) + 200;

        RAISE_APPLICATION_ERROR(
            -20031,
            'Intentional failure after partial modification'
        );
    END change_then_fail;
END nocopy_demo;
/
~~~

Caller:

~~~sql
DECLARE
    l_values nocopy_demo.t_values;
BEGIN
    l_values(1) := 10;
    l_values(2) := 20;

    BEGIN
        nocopy_demo.change_then_fail(l_values);
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE(
                'Error: ' || SQLERRM
            );
    END;

    DBMS_OUTPUT.PUT_LINE('Value 1: ' || l_values(1));
    DBMS_OUTPUT.PUT_LINE('Value 2: ' || l_values(2));
END;
/
~~~

If NOCOPY is applied, the caller may see 110 and 220 even though the procedure raised an exception. If the compiler ignores the hint, the caller may still see 10 and 20 because the procedure did not return normally to perform copy-out.

This example illustrates the non-determinism of whether the compiler applies the hint. Do not use the result of one run on one version as a guarantee for another version or actual argument type.

## 10. Exception Handlers Inside a Procedure Change Copy-Out Behavior

Consider a procedure with an exception handler:

~~~sql
CREATE OR REPLACE PROCEDURE change_and_handle (
    p_value IN OUT NUMBER
) AS
BEGIN
    p_value := p_value + 100;

    RAISE_APPLICATION_ERROR(-20032, 'Test error');
EXCEPTION
    WHEN OTHERS THEN
        -- Handle the error and do not re-raise.
        NULL;
END;
/
~~~

The procedure catches the exception internally and terminates normally. Therefore, under standard copy semantics, the formal parameter's current value is copied out to the actual when the procedure returns.

If the procedure uses IN OUT NOCOPY, the change was already applied directly if the hint was used. Either way, the caller may still receive the modified value because the exception was handled and the procedure returned normally.

This shows that "an exception occurred" is not enough to deduce whether copy-out happened. You must ask whether the exception escaped the subprogram or was handled inside it.

### 10.1 Swallowing Exceptions Can Create False Success

A handler like:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

can trick the caller into thinking the procedure succeeded. If parameter data was partially modified, the caller may continue operating on invalid state.

If valid state cannot be restored, re-raise the error:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Log necessary information if appropriate.
        RAISE;
~~~

Do not catch every exception and ignore it merely to suppress visible errors.

## 11. NOCOPY Does Not Automatically Roll Back PL/SQL Data

An important misconception is that calling ROLLBACK restores all changes made inside a procedure. That applies only to database changes in the transaction, not to in-memory PL/SQL variable values.

Example:

~~~sql
DECLARE
    l_value NUMBER := 10;
BEGIN
    l_value := l_value + 5;
    ROLLBACK;

    DBMS_OUTPUT.PUT_LINE(l_value);
END;
/
~~~

The value of l_value remains 15. ROLLBACK does not restore a PL/SQL variable back to 10.

Similarly, if a procedure uses NOCOPY to modify a collection and then raises an exception, the caller cannot expect a database ROLLBACK to restore the collection. To restore variables, code must save an original copy or compensate the values explicitly.

### 11.1 Database Transactions and Parameters Are Different Scopes

| Type of Change | Undone by Database ROLLBACK? |
|---|---|
| Uncommitted INSERT/UPDATE/DELETE in transaction | Yes |
| NUMBER/VARCHAR2 value in a PL/SQL variable | No |
| Collection elements in PL/SQL memory | No |
| PL/SQL record fields | No |
| Previously COMMITted changes | No |
| External side effects such as email/API | Not automatically |

If a procedure both modifies a NOCOPY parameter and executes DML, an exception can leave two different states: the in-memory parameter modified, while uncommitted DML can be rolled back by the caller. Error contracts must be designed for both scopes.

## 12. Scope of NOCOPY for Collections and Records

NOCOPY is usually most valuable with large structures.

### 12.1 Associative Array

~~~sql
TYPE t_amounts IS TABLE OF NUMBER
    INDEX BY PLS_INTEGER;

PROCEDURE recalculate (
    p_amounts IN OUT NOCOPY t_amounts
);
~~~

A collection can hold many elements; copying the entire structure before and after each call can be expensive.

### 12.2 Nested Table

~~~sql
TYPE t_employee_ids IS TABLE OF NUMBER;

PROCEDURE normalize_ids (
    p_ids IN OUT NOCOPY t_employee_ids
);
~~~

Nested tables can be passed between PL/SQL procedures. Clearly define how empty collections, NULL elements, and element ordering are handled.

### 12.3 VARRAY

~~~sql
TYPE t_scores IS VARRAY(10000) OF NUMBER;

PROCEDURE adjust_scores (
    p_scores IN OUT NOCOPY t_scores
);
~~~

VARRAYs have a maximum element limit and preserve order. With large VARRAYs, NOCOPY can reduce copy overhead if applied by the compiler.

### 12.4 Record

~~~sql
TYPE t_employee_record IS RECORD (
    employee_id NUMBER,
    employee_name VARCHAR2(200),
    salary NUMBER(14,2),
    notes CLOB
);

PROCEDURE update_employee (
    p_employee IN OUT NOCOPY t_employee_record
);
~~~

Records with many fields or large structures can incur copy overhead. Verify formal/actual type compatibility and LOB usage.

### 12.5 Not Every Large Type Automatically Benefits

Data size is one factor, but the compiler also evaluates type, conversions, and call context. Do not conclude NOCOPY is guaranteed to apply simply because a collection has many elements or a record contains a CLOB.

## 13. Aliasing: The Same Variable Passed to Multiple Parameters

A subtle risk of NOCOPY is aliasing: multiple formal parameters referencing the same actual parameter or overlapping memory regions.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE adjust_two_values (
    p_first  IN OUT NOCOPY NUMBER,
    p_second IN OUT NOCOPY NUMBER
) AS
BEGIN
    p_first := p_first + 10;
    p_second := p_second * 2;
END;
/

DECLARE
    l_value NUMBER := 5;
BEGIN
    adjust_two_values(l_value, l_value);
    DBMS_OUTPUT.PUT_LINE(l_value);
END;
/
~~~

In the call above, the same actual L_VALUE is passed to two formal parameters. If both are passed by reference, operations through P_FIRST can affect the value seen by P_SECOND. If the compiler uses a temporary/copy for one parameter, the observed outcome may differ.

Do not rely on any specific update order in aliasing situations. Avoid passing the same actual to multiple OUT/IN OUT parameters when those parameters can write to that data, especially when using NOCOPY.

### 13.1 Aliasing Between Fields or Elements

The risk is not limited to passing the same variable twice. Actual arguments can be related elements or fields of the same structure. When multiple formal parameters can write to overlapping storage, the result depends on passing mechanism and operation order.

Design interfaces so each parameter has independent storage, or pass a single record/collection if fields need to be updated as a unit.

### 13.2 Do Not Use NOCOPY as a Synchronization Mechanism

NOCOPY does not provide locking, transaction isolation, or thread safety. It relates only to how parameters are passed in a PL/SQL call. It does not protect variables from concurrent access via other mechanisms and does not replace synchronization design.

## 14. Designing Error Contracts When Using NOCOPY

Before adding NOCOPY, decide what behavior callers require when a procedure fails.

### 14.1 All-or-Nothing Contract

Requirement: if the procedure fails, the caller must retain the original collection unchanged.

One approach is working on a local copy and only reassigning once all steps succeed:

~~~sql
PROCEDURE transform_safely (
    p_values IN OUT t_values
) AS
    l_work t_values := p_values;
BEGIN
    -- Only modify the working copy.
    FOR i IN 1 .. l_work.COUNT LOOP
        l_work(i) := l_work(i) * 2;
    END LOOP;

    -- Only publish the result after processing completes.
    p_values := l_work;
END transform_safely;
~~~

This pattern has copy overhead, but provides a clearer state contract. If NOCOPY is needed to avoid copy-in/copy-out, you can redesign the API with an upfront validation step and an apply step that avoids predictable errors. Still, runtime errors can happen; true all-or-nothing requires a recovery mechanism.

### 14.2 Contract Allowing Partial Progress

Some batch operations can accept partial results:

- Elements that succeed are kept.
- Elements that fail are recorded in an error list.
- The caller receives total success count and the list of failed items.

In that case, do not let an unexpected exception be the sole mechanism reporting progress. Design explicit outputs, such as a status collection, error list, or result record.

### 14.3 Validate Before Mutating

When possible, perform input validation before modifying the collection:

1. Check that the collection is not NULL/empty as required.
2. Check required indexes and elements.
3. Check value domains.
4. Compute values that might fail.
5. Only then update the data.

Upfront validation reduces mid-flight errors, though it does not eliminate all exceptions such as memory errors or failures from sub-calls.

### 14.4 Manual Restoration on Error

If a procedure has already modified the actual directly via NOCOPY, an exception handler can restore the value if an original copy exists:

~~~sql
PROCEDURE transform_with_restore (
    p_values IN OUT NOCOPY t_values
) AS
    l_original t_values := p_values;
BEGIN
    -- Perform changes on p_values.
    ...
EXCEPTION
    WHEN OTHERS THEN
        p_values := l_original;
        RAISE;
END transform_with_restore;
~~~

This pattern illustrates restoring in-memory contents. The l_original copy incurs memory/copy cost, and reassigning can itself raise errors. Adapt it for the exact collection type and sparse collection handling; ellipses are not runnable PL/SQL statements.

If you no longer gain from NOCOPY after having to copy the entire structure for rollback anyway, omit NOCOPY to keep the contract simpler.

## 15. NOCOPY and Database Transactions

A procedure can accept a NOCOPY collection and simultaneously write to tables:

~~~sql
PROCEDURE apply_batch (
    p_values IN OUT NOCOPY t_values
) AS
BEGIN
    -- Modify the collection in memory.
    p_values(1) := p_values(1) + 1;

    -- Write to the database.
    UPDATE batch_control
    SET processed_count = processed_count + 1
    WHERE batch_id = 10;

    -- An error may occur after the two changes above.
    RAISE_APPLICATION_ERROR(-20040, 'Batch failed');
END apply_batch;
/
~~~

If the caller catches the exception and issues ROLLBACK:

- Uncommitted UPDATE batch_control can be rolled back.
- In-memory changes to p_values are not restored by database ROLLBACK.
- If NOCOPY was applied, the caller may still see modified collection elements.

Therefore, when a procedure combines DML and NOCOPY parameters, design two policies:

1. Transaction policy for database changes.
2. Recovery policy for in-memory data.

Do not assume a single ROLLBACK statement restores the entire program state.

## 16. NOCOPY in Package Specification and Body

If a procedure is declared in a package specification, the declaration in the package body must be compatible with the specification:

~~~sql
CREATE OR REPLACE PACKAGE payroll_api AS
    TYPE t_salary_list IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    PROCEDURE recalculate (
        p_salaries IN OUT NOCOPY t_salary_list
    );
END payroll_api;
/
~~~

~~~sql
CREATE OR REPLACE PACKAGE BODY payroll_api AS
    PROCEDURE recalculate (
        p_salaries IN OUT NOCOPY t_salary_list
    ) AS
    BEGIN
        FOR i IN 1 .. p_salaries.COUNT LOOP
            p_salaries(i) := ROUND(p_salaries(i) * 1.05, 2);
        END LOOP;
    END recalculate;
END payroll_api;
/
~~~

Placing NOCOPY on the public interface clarifies that the API permits compiler parameter-passing optimization. Package consumers must still follow safe exception and aliasing contracts.

Do not add or remove NOCOPY inconsistently between specification and body. When changing public API signatures, recompile dependent objects and verify compatibility.

## 17. NOCOPY and Overloading

Packages can overload procedures by parameter type. NOCOPY is not a data type and must not be used to distinguish overloads. Two signatures differing only in a parameter-passing hint do not form two meaningful type-distinct overloads.

When designing overloads:

- Use data types and parameter count/order to distinguish signatures.
- Keep modes and NOCOPY consistent with the API's intent.
- Avoid signatures where calls become ambiguous due to implicit conversion.

## 18. How to Test NOCOPY

Because NOCOPY is a hint, testing must verify both correctness and performance.

### 18.1 Testing the Success Path

1. Create a collection of representative size.
2. Call the procedure without errors.
3. Verify the caller receives the expected result.
4. Compare versions with and without NOCOPY.

### 18.2 Testing Exceptions After Partial Modification

1. Initialize the actual parameter with known data.
2. Have the procedure modify several elements.
3. Intentionally raise an exception.
4. Catch the exception in the caller.
5. Inspect the actual parameter.
6. Repeat in the target environment/compiler and do not treat partial-update behavior as a guarantee.

The goal is to prove the API does not depend on whether the compiler applies the hint.

### 18.3 Testing Aliasing

Try passing the same actual to multiple OUT/IN OUT parameters. If logic can be affected, revise the API to disallow such calls or add appropriate validation.

### 18.4 Benchmarking

Measure:

- Call duration with small and large collections.
- Memory consumption across repeated calls.
- Real element counts and data types.
- Impact under multiple concurrent sessions.
- Cost of validation and backup copies.

Benchmarks must use identical data, algorithms, compilation settings, and comparable workloads. A difference in a single isolated run is not enough to conclude NOCOPY is always faster.

## 19. Code Patterns to Use and Avoid

### 19.1 Do: Save Results and Control Errors Explicitly

~~~sql
PROCEDURE normalize (
    p_values IN OUT NOCOPY t_values
) AS
BEGIN
    validate_values(p_values);
    normalize_values(p_values);
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END normalize;
~~~

The example above illustrates separating validation from processing while not swallowing exceptions. In real code, explicitly define whether callers accept partial mutation.

### 19.2 Don't: Assume NOCOPY Always Rolls Back on Error

~~~sql
PROCEDURE unsafe_update (
    p_values IN OUT NOCOPY t_values
) AS
BEGIN
    p_values(1) := 999;
    RAISE_APPLICATION_ERROR(-20050, 'Failure');
END;
~~~

Do not design callers assuming that after an exception, p_values will definitely still contain old data. If NOCOPY was applied, changes may have taken effect directly.

### 19.3 Don't: Swallow Exceptions and Continue

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

Callers will not know the operation failed; NOCOPY data may be left in a partial state. Handle errors deliberately and propagate clear results/status.

### 19.4 Don't: Alias the Same Actual Across Multiple Writable Parameters

~~~sql
update_two_values(
    p_first  => l_values,
    p_second => l_values
);
~~~

If both parameters are writable and use NOCOPY, avoid aliasing calls. Use two separate variables or a single record parameter holding the fields to update.

## 20. Deciding Whether to Use NOCOPY

| Condition | Recommendation |
|---|---|
| Parameter is a large collection/record with measurable copy overhead | Worth testing NOCOPY |
| Parameter is a small scalar | Usually unnecessary |
| API must preserve the actual unchanged if an error occurs | Prefer copy semantics or design in-memory rollback explicitly |
| API permits partial progress | Can use NOCOPY if callers are clearly informed of state |
| Same actual may be passed to multiple writable parameters | Avoid NOCOPY/aliasing or revise the interface |
| Actual type requires conversion | Do not assume compiler will apply NOCOPY |
| No benchmark exists yet | No basis yet to add the hint |
| Code depends strictly on the hint being applied | Redesign because the hint is not guaranteed |

## 21. Common Errors and Misconceptions

| Misconception or Symptom | Cause | How to Handle |
|---|---|---|
| NOCOPY guarantees pass-by-reference | NOCOPY is only a hint | Write code that works even if the hint is ignored |
| Exceptions always leave actual unchanged | Reference passing may have written directly to actual | Define a recovery contract |
| ROLLBACK restores collections | ROLLBACK only handles database changes in the transaction | Restore variables/collections manually |
| Procedure catches exception and returns normally, yet caller sees unexpected changes | Exception was handled, so copy-out can occur | Check whether the handler swallows errors and restores data |
| Passing the same variable to two parameters produces unpredictable results | Aliasing between formal parameters | Avoid passing the same actual to multiple writable parameters |
| Adding NOCOPY always speeds up algorithms dramatically | Bottleneck may lie in internal logic or SQL | Benchmark the full workload |
| NOCOPY works with IN | Hint is for OUT/IN OUT | Choose the appropriate mode |
| Large parameters are always passed by reference | Compiler may need temporaries or conversions | Do not assume passing mechanism |
| Exception handlers automatically roll back data | Exceptions do not roll back PL/SQL variables | Manage variables and transactions separately |

## 22. Self-Check Practice Exercises

Exercises should be run in a test schema using PL/SQL collections/records.

### Exercise 1 — OUT and IN OUT

Write two procedures: one OUT procedure returning a row count, and one IN OUT procedure incrementing an input value. Call them from an anonymous block and observe caller variables after normal return.

### Exercise 2 — Copy Semantics on Exception

Write an IN OUT procedure without NOCOPY that modifies the formal parameter and then raises an unhandled internal exception. Catch the error in the caller and inspect the actual parameter.

### Exercise 3 — NOCOPY and Partial Mutation

Repeat Exercise 2 with NOCOPY on a collection. Inspect the actual parameter after the error. Explain why the result cannot be treated as guaranteed across all compiler contexts.

### Exercise 4 — Internal Exception Handler

Catch the exception inside the procedure and return normally. Compare with re-raising the exception. Explain the effect on copy-out.

### Exercise 5 — Large Collection

Create a collection with many elements and write two procedures running the same algorithm with and without NOCOPY. Benchmark execution time and memory under equivalent conditions.

### Exercise 6 — Aliasing

Pass the same variable to two IN OUT parameters. Test with and without NOCOPY. Record the resulting values and explain why an API should not rely on update order during aliasing.

### Exercise 7 — Database Rollback Does Not Roll Back Variables

In the same block, modify a collection, run a table UPDATE, and then raise an exception. Catch the error, issue ROLLBACK, and inspect both table data and the collection.

### Exercise 8 — All-or-Nothing

Design a procedure that processes a collection using a local working copy, reassigning the parameter only when all steps succeed. Compare safety and copy cost against NOCOPY.

### Exercise 9 — Partial Progress

Design a procedure returning the count of succeeded elements and a list of failed elements instead of raising an exception on the first item. Define the caller contract for receiving partial results.

### Exercise 10 — Package API

Place the collection type and NOCOPY procedure in a package specification/body. Compile, call from an anonymous block, and inspect signature errors when declarations are inconsistent.

## 23. Checklist Before Putting NOCOPY into Production

- Is the parameter OUT or IN OUT and large enough for copying cost to matter?
- Is there a benchmark proving a benefit?
- Does the code remain correct when the compiler ignores NOCOPY?
- Do callers know the parameter state after an exception?
- Must the actual parameter remain unchanged when the procedure fails?
- Are PL/SQL variables and database transactions handled separately?
- Do any exception handlers swallow errors or return normally after partial processing?
- Is it possible for the same actual to be passed to multiple writable parameters?
- Does any actual argument require conversion or a temporary?
- Do the package specification and body have compatible declarations?
- Does the API document partial progress and error semantics?
- Has it been tested with representative collection/record sizes and multiple sessions?

## 24. Key Takeaways

| Concept | Practical Rule |
|---|---|
| IN | Receives data for reading |
| OUT | Returns data produced by the subprogram |
| IN OUT | Receives old value and returns new value |
| NOCOPY | Hint allowing the compiler to pass OUT/IN OUT by reference |
| Copy semantics | Standard copy-out occurs when the subprogram returns normally |
| Escaping exception | Standard copy-out does not occur |
| NOCOPY applied | Directly written changes may remain in actual after an exception |
| Hint ignored | Behaves according to copy semantics |
| PL/SQL variable | Not restored by database ROLLBACK |
| Aliasing | Passing the same actual to multiple writable parameters can cause unpredictable behavior |
| Performance | Only add NOCOPY when benchmarks demonstrate a benefit |
| Error contract | Must specify all-or-nothing vs. allowing partial progress |

NOCOPY can reduce copy overhead for large collections and records, but it also changes what callers may observe when a procedure fails. Because the compiler has the right to ignore the hint, write code that is correct in both cases. In particular, separate PL/SQL variable mutations from database transactions, avoid aliasing, do not swallow exceptions, and clearly specify what state callers should expect when processing completes only partially.
